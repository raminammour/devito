import numpy as np

from conftest import assert_structure, get_params, get_arrays, check_array
from devito import Buffer, Eq, Function, TimeFunction, Grid, Operator, cos, sin
from devito.types import Symbol


class TestBasic(object):

    def test_v0(self):
        grid = Grid(shape=(10, 10, 10))

        f = Function(name='f', grid=grid, space_order=4)
        u = TimeFunction(name='u', grid=grid, space_order=4)
        u1 = TimeFunction(name='u', grid=grid, space_order=4)

        eqn = Eq(u.forward, (u*cos(f)).dx + 1.)

        op0 = Operator(eqn)
        op1 = Operator(eqn, opt=('advanced', {'expand': False}))

        # Check generated code
        for op in [op0, op1]:
            xs, ys, zs = get_params(op, 'x_size', 'y_size', 'z_size')
            arrays = [i for i in get_arrays(op) if i._mem_heap]
            assert len(arrays) == 1
            check_array(arrays[0], ((2, 2), (0, 0), (0, 0)), (xs+4, ys, zs))

        op0.apply(time_M=10)
        op1.apply(time_M=10, u=u1)

        assert np.allclose(u.data, u1.data, rtol=10e-6)

    def test_fusion_after_unexpansion(self):
        grid = Grid(shape=(10, 10))

        u = TimeFunction(name='u', grid=grid, space_order=4)

        eqn = Eq(u.forward, u.dx + u.dy)

        op = Operator(eqn, opt=('advanced', {'expand': False}))

        assert op._profiler._sections['section0'].sops == 21
        assert_structure(op, ['t,x,y', 't,x,y,i0'], 't,x,y,i0')

    def test_v1(self):
        grid = Grid(shape=(10, 10, 10))

        f = Function(name='f', grid=grid, space_order=4)
        u = TimeFunction(name='u', grid=grid, space_order=4)
        v = TimeFunction(name='v', grid=grid, space_order=4)
        u1 = TimeFunction(name='u', grid=grid, space_order=4)
        v1 = TimeFunction(name='v', grid=grid, space_order=4)

        eqns = [Eq(u.forward, (u*cos(f)).dx + v + 1.),
                Eq(v.forward, (v*cos(f)).dy + u.forward.dx + 1.)]

        op0 = Operator(eqns)
        op1 = Operator(eqns, opt=('advanced', {'expand': False}))

        # Check generated code
        for op in [op0, op1]:
            xs, ys, zs = get_params(op, 'x_size', 'y_size', 'z_size')
            arrays = get_arrays(op)
            assert len(arrays) == 1
            check_array(arrays[0], ((2, 2), (2, 2), (0, 0)), (xs+4, ys+4, zs))
        assert op1._profiler._sections['section1'].sops == 44

        op0.apply(time_M=10)
        op1.apply(time_M=10, u=u1, v=v1)

        assert np.allclose(u.data, u1.data, rtol=10e-5)
        assert np.allclose(v.data, v1.data, rtol=10e-5)

    def test_v2(self):
        grid = Grid(shape=(10, 10, 10))

        u = TimeFunction(name='u', grid=grid, space_order=4)
        v = TimeFunction(name='v', grid=grid, space_order=4)
        u1 = TimeFunction(name='u', grid=grid, space_order=4)
        v1 = TimeFunction(name='v', grid=grid, space_order=4)

        eqns = [Eq(u.forward, (u.dx.dy + v*u.dx + 1.)),
                Eq(v.forward, (v.dy.dx + u.dx.dz + 1.))]

        op0 = Operator(eqns)
        op1 = Operator(eqns, opt=('advanced', {'expand': False,
                                               'blocklevels': 0}))

        # Check generated code -- expect maximal fusion!
        assert_structure(op1,
                         ['t,x,y,z', 't,x,y,z,i0', 't,x,y,z,i1', 't,x,y,z,i1,i0'],
                         't,x,y,z,i0,i1,i0')

        op0.apply(time_M=5)
        op1.apply(time_M=5, u=u1, v=v1)

        assert np.allclose(u.data, u1.data, rtol=10e-3)
        assert np.allclose(v.data, v1.data, rtol=10e-3)

    def test_v3(self):
        grid = Grid(shape=(10, 10, 10))

        u = TimeFunction(name='u', grid=grid, space_order=4)
        v = TimeFunction(name='v', grid=grid, space_order=4)
        u1 = TimeFunction(name='u', grid=grid, space_order=4)
        v1 = TimeFunction(name='v', grid=grid, space_order=4)

        eqns = [Eq(u.forward, (u.dx.dy + v*u + 1.)),
                Eq(v.forward, (v + u.dx.dy + 1.))]

        op0 = Operator(eqns)
        op1 = Operator(eqns, opt=('advanced', {'expand': False}))

        # Check generated code -- redundant IndexDerivatives have been caught!
        op1._profiler._sections['section0'].sops == 65

        op0.apply(time_M=5)
        op1.apply(time_M=5, u=u1, v=v1)

        assert np.allclose(u.data, u1.data, rtol=10e-3)
        assert np.allclose(v.data, v1.data, rtol=10e-3)

    def test_v4(self):
        grid = Grid(shape=(16, 16, 16))
        t = grid.stepping_dim
        x, y, z = grid.dimensions

        so = 4

        a = Function(name='a', grid=grid, space_order=so)
        f = Function(name='f', grid=grid, space_order=so)
        e = Function(name='e', grid=grid, space_order=so)
        r = Function(name='r', grid=grid, space_order=so)
        p0 = TimeFunction(name='p0', grid=grid, time_order=2, space_order=so)
        m0 = TimeFunction(name='m0', grid=grid, time_order=2, space_order=so)

        def g1(field, r, e):
            return (cos(e) * cos(r) * field.dx(x0=x+x.spacing/2) +
                    cos(e) * sin(r) * field.dy(x0=y+y.spacing/2) -
                    sin(e) * field.dz(x0=z+z.spacing/2))

        def g2(field, r, e):
            return - (sin(r) * field.dx(x0=x+x.spacing/2) -
                      cos(r) * field.dy(x0=y+y.spacing/2))

        def g3(field, r, e):
            return (sin(e) * cos(r) * field.dx(x0=x+x.spacing/2) +
                    sin(e) * sin(r) * field.dy(x0=y+y.spacing/2) +
                    cos(e) * field.dz(x0=z+z.spacing/2))

        def g1_tilde(field, r, e):
            return ((cos(e) * cos(r) * field).dx(x0=x-x.spacing/2) +
                    (cos(e) * sin(r) * field).dy(x0=y-y.spacing/2) -
                    (sin(e) * field).dz(x0=z-z.spacing/2))

        def g2_tilde(field, r, e):
            return - ((sin(r) * field).dx(x0=x-x.spacing/2) -
                      (cos(r) * field).dy(x0=y-y.spacing/2))

        def g3_tilde(field, r, e):
            return ((sin(e) * cos(r) * field).dx(x0=x-x.spacing/2) +
                    (sin(e) * sin(r) * field).dy(x0=y-y.spacing/2) +
                    (cos(e) * field).dz(x0=z-z.spacing/2))

        update_p = t.spacing**2 * a**2 / f * \
            (g1_tilde(f * g1(p0, r, e), r, e) +
             g2_tilde(f * g2(p0, r, e), r, e) +
             g3_tilde(f * g3(p0, r, e) + f * g3(m0, r, e), r, e)) + \
            (2 - t.spacing * a)

        update_m = t.spacing**2 * a**2 / f * \
            (g1_tilde(f * g1(m0, r, e), r, e) +
             g2_tilde(f * g2(m0, r, e), r, e) +
             g3_tilde(f * g3(m0, r, e) + f * g3(p0, r, e), r, e)) + \
            (2 - t.spacing * a)

        eqns = [Eq(p0.forward, update_p),
                Eq(m0.forward, update_m)]

        op = Operator(eqns, subs=grid.spacing_map,
                      opt=('advanced', {'expand': False}))

        # Check code generation
        assert op._profiler._sections['section1'].sops == 1442
        assert_structure(op, ['x,y,z',
                              't,x0_blk0,y0_blk0,x,y,z',
                              't,x0_blk0,y0_blk0,x,y,z,i1',
                              't,x0_blk0,y0_blk0,x,y,z,i1,i0'],
                         'x,y,z,t,x0_blk0,y0_blk0,x,y,z,i1,i0')

        op.cfunction

    def test_v5(self):
        grid = Grid(shape=(16, 16))

        p0 = TimeFunction(name='p0', grid=grid, time_order=2, space_order=4,
                          save=Buffer(2))
        m0 = TimeFunction(name='m0', grid=grid, time_order=2, space_order=4,
                          save=Buffer(2))

        eqns = [Eq(p0.forward, (p0.dx + m0.dx).dx + p0.backward),
                Eq(m0.forward, m0.dx.dx + m0.backward)]

        op = Operator(eqns, subs=grid.spacing_map,
                      opt=('advanced', {'expand': False}))

        # Check code generation
        assert op._profiler._sections['section0'].sops == 127
        assert_structure(op, ['t,x,y', 't,x,y,i1', 't,x,y,i1,i0'], 't,x,y,i1,i0')

        op.cfunction

    def test_v6(self):
        grid = Grid(shape=(16, 16))

        f = Function(name='f', grid=grid, space_order=4)
        p0 = TimeFunction(name='p0', grid=grid, time_order=2, space_order=4,
                          save=Buffer(2))
        m0 = TimeFunction(name='m0', grid=grid, time_order=2, space_order=4,
                          save=Buffer(2))

        s0 = Symbol(name='s0', dtype=np.float32)

        eqns = [Eq(p0.forward, (p0.dx + m0.dx).dx + p0.backward),
                Eq(s0, 4., implicit_dims=p0.dimensions),
                Eq(m0.forward, (m0.dx + s0).dx + f*m0.backward)]

        op = Operator(eqns, subs=grid.spacing_map,
                      opt=('advanced', {'expand': False}))

        # Check code generation
        assert op._profiler._sections['section0'].sops == 133
        assert_structure(op, ['t,x,y', 't,x,y,i1', 't,x,y,i1,i0'], 't,x,y,i1,i0')

        op.cfunction
