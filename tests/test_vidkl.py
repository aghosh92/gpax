import sys
import pytest
import numpy as onp
import jax.numpy as jnp
import jax
import haiku as hk
import numpyro
from numpy.testing import assert_equal

sys.path.append("../../../")

from gpax.vidkl import viDKL, MLP
from gpax.utils import get_keys, get_haiku_dict


def get_dummy_data(jax_ndarray=True):
    X = onp.random.randn(21, 36)
    y = onp.random.randn(21,)
    if jax_ndarray:
        return jnp.array(X), jnp.array(y)
    return X, y


def get_dummy_vector_data(jax_ndarray=True):
    X, y = get_dummy_data(jax_ndarray)
    X = X[None].repeat(3, axis=0)
    y = y[None].repeat(3, axis=0)
    return X, y


def get_dummy_nn_params():
    rng_key = get_keys()[0]
    X, y = get_dummy_data()
    mlp = MLP()
    net = hk.transform(lambda x: mlp()(x))
    params = net.init(rng_key, X, y)


@pytest.mark.parametrize("jax_ndarray", [True, False])
def test_single_fit(jax_ndarray):
    X, y = get_dummy_data(jax_ndarray)
    rng_key = get_keys()[0]
    m = viDKL(X.shape[-1])
    nn_params, kernel_params, losses = m.single_fit(
        rng_key, X, y, num_steps=100, step_size=0.05)
    assert isinstance(kernel_params, dict)
    assert isinstance(nn_params, dict)
    assert isinstance(losses, jnp.ndarray)


def test_get_mvn_posterior():
    rng_key = get_keys()[0]
    X, y = get_dummy_data()
    X_test, _ = get_dummy_data()
    net = hk.transform(lambda x: MLP()(x))
    nn_params = net.init(rng_key, X)
    kernel_params = {"k_length": jnp.array([1.0]),
                     "k_scale": jnp.array(1.0),
                     "noise": jnp.array(0.1)}
    m = viDKL(X.shape[-1])
    mean, cov = m.get_mvn_posterior(X, y, X_test, nn_params, kernel_params)
    assert isinstance(mean, jnp.ndarray)
    assert isinstance(cov, jnp.ndarray)
    assert_equal(mean.shape, (X_test.shape[0],))
    assert_equal(cov.shape, (X_test.shape[0], X_test.shape[0]))


def test_fit_scalar_target():
    X, y = get_dummy_data()
    rng_key = get_keys()[0]
    m = viDKL(X.shape[-1])
    m.fit(rng_key, X, y, num_steps=100, step_size=0.05)
    for v in m.kernel_params.values():
        assert v.ndim < 2
    for val in m.nn_params.values():
        for v in val.values():
            assert v.ndim < 3

def test_fit_vector_target():
    X, y = get_dummy_vector_data()
    rng_key = get_keys()[0]
    m = viDKL(X.shape[-1])
    m.fit(rng_key, X, y, num_steps=100, step_size=0.05)
    for v in m.kernel_params.values():
        assert v.ndim > 0
        assert_equal(v.shape[0], 3)
    for val in m.nn_params.values():
        for v in val.values():
            assert v.ndim > 1
            assert_equal(v.shape[0], 3)


def test_predict_scalar():
    rng_key = get_keys()[0]
    X, y = get_dummy_data()
    X_test, _ = get_dummy_data()
    net = hk.transform(lambda x: MLP()(x))
    nn_params = net.init(rng_key, X)
    kernel_params = {"k_length": jnp.array([1.0]),
                     "k_scale": jnp.array(1.0),
                     "noise": jnp.array(0.1)}
    m = viDKL(X.shape[-1])
    m.X_train = X
    m.y_train = y
    m.nn_params = nn_params
    m.kernel_params = kernel_params
    mean, var = m.predict(rng_key, X_test)
    assert isinstance(mean, jnp.ndarray)
    assert isinstance(var, jnp.ndarray)
    assert_equal(mean.shape, (len(X_test),))
    assert_equal(var.shape, (len(X_test),))


def test_predict_vector():
    rng_key = get_keys()[0]
    X, y = get_dummy_vector_data()
    X_test, _ = get_dummy_vector_data()
    net = hk.transform(lambda x: MLP()(x))
    clone = lambda x: net.init(rng_key, x)
    nn_params = jax.vmap(clone)(X)
    kernel_params = {"k_length": jnp.array([[1.0], [1.0], [1.0]]),
                     "k_scale": jnp.array([1.0, 1.0, 1.0]),
                     "noise": jnp.array([0.1, 0.1, 0.1])}
    m = viDKL(X.shape[-1])
    m.X_train = X
    m.y_train = y
    m.nn_params = nn_params
    m.kernel_params = kernel_params
    mean, var = m.predict(rng_key, X_test)
    assert isinstance(mean, jnp.ndarray)
    assert isinstance(var, jnp.ndarray)
    assert_equal(mean.shape, X_test.shape[:-1])
    assert_equal(var.shape, X_test.shape[:-1])


def test_predict_in_batches_scalar():
    rng_key = get_keys()[0]
    X, y = get_dummy_data()
    X_test, _ = get_dummy_data()
    net = hk.transform(lambda x: MLP()(x))
    nn_params = net.init(rng_key, X)
    kernel_params = {"k_length": jnp.array([1.0]),
                     "k_scale": jnp.array(1.0),
                     "noise": jnp.array(0.1)}
    m = viDKL(X.shape[-1])
    m.X_train = X
    m.y_train = y
    m.nn_params = nn_params
    m.kernel_params = kernel_params
    mean, var = m.predict_in_batches(rng_key, X_test, batch_size=10)
    assert isinstance(mean, jnp.ndarray)
    assert isinstance(var, jnp.ndarray)
    assert_equal(mean.shape, (len(X_test),))
    assert_equal(var.shape, (len(X_test),))


def test_predict_in_batches_vector():
    rng_key = get_keys()[0]
    X, y = get_dummy_vector_data()
    X_test, _ = get_dummy_vector_data()
    net = hk.transform(lambda x: MLP()(x))
    clone = lambda x: net.init(rng_key, x)
    nn_params = jax.vmap(clone)(X)
    kernel_params = {"k_length": jnp.array([[1.0], [1.0], [1.0]]),
                     "k_scale": jnp.array([1.0, 1.0, 1.0]),
                     "noise": jnp.array([0.1, 0.1, 0.1])}
    m = viDKL(X.shape[-1])
    m.X_train = X
    m.y_train = y
    m.nn_params = nn_params
    m.kernel_params = kernel_params
    mean, var = m.predict_in_batches(rng_key, X_test, batch_size=10)
    assert isinstance(mean, jnp.ndarray)
    assert isinstance(var, jnp.ndarray)
    assert_equal(mean.shape, X_test.shape[:-1])
    assert_equal(var.shape, X_test.shape[:-1])


def test_fit_predict_scalar():
    rng_key = get_keys()[0]
    X, y = get_dummy_data()
    X_test, _ = get_dummy_data()
    m = viDKL(X.shape[-1])
    mean, var = m.fit_predict(
        rng_key, X, y, X_test, num_steps=100, step_size=0.05, batch_size=10)
    assert isinstance(mean, jnp.ndarray)
    assert isinstance(var, jnp.ndarray)
    assert_equal(mean.shape, (len(X_test),))
    assert_equal(var.shape, (len(X_test),))


def test_fit_predict_vector():
    rng_key = get_keys()[0]
    X, y = get_dummy_vector_data()
    X_test, _ = get_dummy_vector_data()
    m = viDKL(X.shape[-1])
    mean, var = m.fit_predict(
        rng_key, X, y, X_test, num_steps=100, step_size=0.05, batch_size=10)
    assert isinstance(mean, jnp.ndarray)
    assert isinstance(var, jnp.ndarray)
    assert_equal(mean.shape, X_test.shape[:-1])
    assert_equal(var.shape, X_test.shape[:-1])


def test_fit_predict_scalar_ensemble():
    rng_key = get_keys()[0]
    X, y = get_dummy_data()
    X_test, _ = get_dummy_data()
    m = viDKL(X.shape[-1])
    mean, var = m.fit_predict(
        rng_key, X, y, X_test, n_models=4,
        num_steps=100, step_size=0.05, batch_size=10)
    assert isinstance(mean, jnp.ndarray)
    assert isinstance(var, jnp.ndarray)
    assert_equal(mean.shape, (4, len(X_test),))
    assert_equal(var.shape, (4, len(X_test),))


def test_fit_predict_vector_ensemble():
    rng_key = get_keys()[0]
    X, y = get_dummy_vector_data()
    X_test, _ = get_dummy_vector_data()
    m = viDKL(X.shape[-1])
    mean, var = m.fit_predict(
        rng_key, X, y, X_test, n_models=2,
        num_steps=100, step_size=0.05, batch_size=10)
    assert isinstance(mean, jnp.ndarray)
    assert isinstance(var, jnp.ndarray)
    assert_equal(mean.shape, (2, *X_test.shape[:-1]))
    assert_equal(var.shape, (2, *X_test.shape[:-1]))
