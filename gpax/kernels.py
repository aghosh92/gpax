"""
kernels.py
==========

Kernel functions

Created by Maxim Ziatdinov (email: maxim.ziatdinov@ai4microscopy.com)
"""

from typing import Union, Dict, Callable

import math

import jax.numpy as jnp
from jax import jit, vmap

kernel_fn_type = Callable[[jnp.ndarray, jnp.ndarray, Dict[str, jnp.ndarray], jnp.ndarray],  jnp.ndarray]


def _sqrt(x, eps=1e-12):
    return jnp.sqrt(x + eps)


def add_jitter(x, jitter=1e-6):
    return x + jitter


def square_scaled_distance(X: jnp.ndarray, Z: jnp.ndarray,
                           lengthscale: Union[jnp.ndarray, float] = 1.
                           ) -> jnp.ndarray:
    r"""
    Computes a square of scaled distance, :math:`\|\frac{X-Z}{l}\|^2`,
    between X and Z are vectors with :math:`n x num_features` dimensions
    """
    scaled_X = X / lengthscale
    scaled_Z = Z / lengthscale
    X2 = (scaled_X ** 2).sum(1, keepdims=True)
    Z2 = (scaled_Z ** 2).sum(1, keepdims=True)
    XZ = jnp.matmul(scaled_X, scaled_Z.T)
    r2 = X2 - 2 * XZ + Z2.T
    return r2.clip(0)


@jit
def RBFKernel(X: jnp.ndarray, Z: jnp.ndarray,
              params: Dict[str, jnp.ndarray],
              noise: int = 0, **kwargs: float) -> jnp.ndarray:
    """
    Radial basis function kernel

    Args:
        X: 2D vector with *(number of points, number of features)* dimension
        Z: 2D vector with *(number of points, number of features)* dimension
        params: Dictionary with kernel hyperparameters 'k_length' and 'k_scale'
        noise: optional noise vector with dimension (n,)

    Returns:
        Computed kernel matrix betwenen X and Z
    """
    r2 = square_scaled_distance(X, Z, params["k_length"])
    k = params["k_scale"] * jnp.exp(-0.5 * r2)
    if X.shape == Z.shape:
        k += add_jitter(noise, **kwargs) * jnp.eye(X.shape[0])
    return k


@jit
def MaternKernel(X: jnp.ndarray, Z: jnp.ndarray,
                 params: Dict[str, jnp.ndarray],
                 noise: int = 0, **kwargs: float) -> jnp.ndarray:
    """
    Matern52 kernel

    Args:
        X: 2D vector with *(number of points, number of features)* dimension
        Z: 2D vector with *(number of points, number of features)* dimension
        params: Dictionary with kernel hyperparameters 'k_length' and 'k_scale'
        noise: optional noise vector with dimension (n,)

    Returns:
        Computed kernel matrix between X and Z
    """
    r2 = square_scaled_distance(X, Z, params["k_length"])
    r = _sqrt(r2)
    sqrt5_r = 5**0.5 * r
    k = params["k_scale"] * (1 + sqrt5_r + (5/3) * r2) * jnp.exp(-sqrt5_r)
    if X.shape == Z.shape:
        k += add_jitter(noise, **kwargs) * jnp.eye(X.shape[0])
    return k


@jit
def PeriodicKernel(X: jnp.ndarray, Z: jnp.ndarray,
                   params: Dict[str, jnp.ndarray],
                   noise: int = 0, **kwargs: float
                   ) -> jnp.ndarray:
    """
    Periodic kernel

    Args:
        X: 2D vector with *(number of points, number of features)* dimension
        Z: 2D vector with *(number of points, number of features)* dimension
        params: Dictionary with kernel hyperparameters 'k_length', 'k_scale', and 'period'
        noise: optional noise vector with dimension (n,)

    Returns:
        Computed kernel matrix between X and Z
    """
    d = X[:, None] - Z[None]
    scaled_sin = jnp.sin(math.pi * d / params["period"]) / params["k_length"]
    k = params["k_scale"] * jnp.exp(-2 * (scaled_sin ** 2).sum(-1))
    if X.shape == Z.shape:
        k += add_jitter(noise, **kwargs) * jnp.eye(X.shape[0])
    return k


def nngp_erf(x1: jnp.ndarray, x2: jnp.ndarray,
             var_b: jnp.array, var_w: jnp.array,
             depth: int = 3) -> jnp.array:
    """
    Computes the Neural Network Gaussian Process (NNGP) kernel value for
    a single pair of inputs using the Erf activation.

    Args:
        x1: First input vector.
        x2: Second input vector.
        var_b: Bias variance.
        var_w: Weight variance.
        depth: The number of layers in the corresponding infinite-width neural network.
               Controls the level of recursion in the computation.

    Returns:
        Kernel value for the pair of inputs.
    """
    d = x1.shape[-1]
    if depth == 0:
        return var_b + var_w * jnp.sum(x1 * x2, axis=-1) / d
    else:
        K_12 = nngp_erf(x1, x2, var_b, var_w, depth - 1)
        K_11 = nngp_erf(x1, x1, var_b, var_w, depth - 1)
        K_22 = nngp_erf(x2, x2, var_b, var_w, depth - 1)
        sqrt_term = jnp.sqrt((1 + 2 * K_11) * (1 + 2 * K_22))
        fraction = 2 * K_12 / sqrt_term
        epsilon = 1e-7
        theta = jnp.arcsin(jnp.clip(fraction, a_min=-1 + epsilon, a_max=1 - epsilon))
        result = var_b + 2 * var_w / jnp.pi * theta
        return result


def nngp_relu(x1: jnp.ndarray, x2: jnp.ndarray,
              var_b: jnp.array, var_w: jnp.array,
              depth: int = 3) -> jnp.array:
    """
    Computes the Neural Network Gaussian Process (NNGP) kernel value for
    a single pair of inputs using RELU activation.

    Args:
        x1: First input vector.
        x2: Second input vector.
        var_b: Bias variance.
        var_w: Weight variance.
        depth: The number of layers in the corresponding infinite-width neural network.
               Controls the level of recursion in the computation.

    Returns:
        Kernel value for the pair of inputs.
    """
    eps = 1e-7
    d = x1.shape[-1]
    if depth == 0:
        return var_b + var_w * jnp.sum(x1 * x2, axis=-1) / d
    else:
        K_12 = nngp_relu(x1, x2, var_b, var_w, depth - 1, )
        K_11 = nngp_relu(x1, x1, var_b, var_w, depth - 1, )
        K_22 = nngp_relu(x2, x2, var_b, var_w, depth - 1, )
        sqrt_term = jnp.sqrt(K_11 * K_22)
        fraction = K_12 / sqrt_term
        theta = jnp.arccos(jnp.clip(fraction, a_min=-1 + eps, a_max=1 - eps))
        theta_term = jnp.sin(theta) + (jnp.pi - theta) * fraction
        return var_b + var_w / (2 * jnp.pi) * sqrt_term * theta_term


def NNGPKernel(activation: str = 'erf', depth: int = 3
               ) -> Callable[[jnp.ndarray, jnp.ndarray, Dict[str, jnp.ndarray]], jnp.ndarray]:
    """
    Neural Network Gaussian Process (NNGP) kernel function

    Args:
        activation: activation function ('erf' or 'relu')
        depth: The number of layers in the corresponding infinite-width neural network.
               Controls the level of recursion in the computation.

    Returns:
        Function for computing kernel matrix between X and Z.
    """
    nngp_single_pair_ = nngp_relu if activation == 'relu' else nngp_erf

    def NNGPKernel_func(X: jnp.ndarray, Z: jnp.ndarray,
                        params: Dict[str, jnp.ndarray],
                        noise: jnp.ndarray = 0, **kwargs
                        ) -> jnp.ndarray:
        """
        Computes the Neural Network Gaussian Process (NNGP) kernel.

        Args:
            X: First set of input vectors.
            Z: Second set of input vectors.
            params: Dictionary containing bias variance and weight variance

        Returns:
            Computed kernel matrix between X and Z.
        """
        var_b = params["var_b"]
        var_w = params["var_w"]
        k = vmap(lambda x: vmap(lambda z: nngp_single_pair_(x, z, var_b, var_w, depth))(Z))(X)
        if X.shape == Z.shape:
            k += add_jitter(noise, **kwargs) * jnp.eye(X.shape[0])
        return k

    return NNGPKernel_func


def index_kernel(indices1, indices2, params):
    r"""
    Computes the task kernel matrix for given task indices.
    The task covariance between two discrete indices i and j
    is calculated as:

    .. math::
        task\_kernel_values[i, j] = WW^T[i, j] + v[i] \delta_{ij}

    where :math:`WW^T` is the matrix product of :math:`B` with its transpose, :math:`v[i]`
    is the variance of task :math:`i`, and :math:`\delta_{ij}` is the Kronecker delta
    which is 1 if :math:`i == j` and 0 otherwise.

    Args:
        indices1:
            An array of task indices for the first set of data points.
            Each entry is an integer that indicates the task associated
            with a data point.
        indices2:
            An array of task indices for the second set of data points.
            Each entry is an integer that indicates the task associated
            with a data point.
        params:
            Dictionary of parameters for the task kernel. It includes:
            'W': The coregionalization matrix of shape (num_tasks, num_tasks).
                This is a symmetric positive  semi-definite matrix that determines
                the correlation structure between the tasks.
            'v':
                The vector of task variances with the (n_tasks,) shape.
                This is a diagonal matrix that  determines the variance of each task.

    Returns:
        Computed kernel matrix of the shape (len(indices1), len(indices2)).
        Each entry task_kernel_values[i, j] is the covariance between the tasks
        associated with data point i in indices1 and data point j in indices2.
    """
    W = params["W"]
    v = params["v"]
    B = jnp.dot(W, W.T) + jnp.diag(v)
    return B[jnp.ix_(indices1, indices2)]


def MultitaskKernel(base_kernel, **kwargs1):
    r"""
    Constructs a multi-task kernel given a base data kernel.
    The multi-task kernel is defined as

    .. math::
        K(x_i, y_j) = k_{data}(x, y) * k_{task}(i, j)

    where *x* and *y* are data points and *i* and *j* are the tasks
    associated with these points. The task indices are passed as the
    last column in the input data vectors.

    Args:
        base_kernel:
            The name of the base data kernel or a function that computes
            the base data kernel. This kernel is used to compute the
            similarities in the input space. The built-in kernels are 'RBF',
            'Matern', 'Periodic', and 'NNGP'.

        **kwargs1:
            Additional keyword arguments to pass to the `get_kernel`
            function when constructing the base data kernel.

    Returns:
        The constructed multi-task kernel function.
    """

    data_kernel = get_kernel(base_kernel, **kwargs1)

    def multi_task_kernel(X, Z, params, noise=0, **kwargs2):
        """
        Computes multi-task kernel matrix, given two input arrays and
        a dictionary wuth kernel parameters. The input arrays must have the
        shape (N, D+1) where N is the number of data points and D is the feature
        dimension. The last column contains task indices.
        """

        # Extract input data and task indices from X and Z
        X_data, indices_X = X[:, :-1], X[:, -1].astype(int)
        Z_data, indices_Z = Z[:, :-1], Z[:, -1].astype(int)

        # Compute data and task kernels
        k_data = data_kernel(X_data, Z_data, params, 0, **kwargs2) # noise will be added later
        k_task = index_kernel(indices_X, indices_Z, params)

        # Compute the multi-task kernel
        K = k_data * k_task

        # Add noise associated with each task
        if X.shape == Z.shape:
            # Get the noise corresponding to each sample's task
            if isinstance(noise, (int, float)):
                noise = jnp.ones(1) * noise
            sample_noise = noise[indices_X]
            # Add small jitter for numerical stability
            sample_noise = add_jitter(sample_noise, **kwargs2)
            # Add the noise to the diagonal of the kernel matrix
            K = K.at[jnp.diag_indices(K.shape[0])].add(sample_noise)

        return K

    return multi_task_kernel


def MultivariateKernel(base_kernel, num_tasks, **kwargs1):
    r"""
    Construct a multivariate kernel given a base data kernel asssuming
    that all tasks share the same input space. For situations where not all
    tasks share the same input parameters, see MultitaskKernel.
    The multivariate kernel is defined as a Kronecker product between
    data and task kernels

    .. math::
        K(x_i, y_j) = k_{data}(x, y) * k_{task}(i, j)

    where *x* and *y* are data points and *i* and *j* are the tasks
    associated with these points.

    Args:
        base_kernel:
            The name of the base data kernel or a function that computes
            the base data kernel. This kernel is used to compute the
            similarities in the input space. THe built-in kernels are 'RBF',
            'Matern', 'Periodic', and 'NNGP'.
        num_tasks:
            number of tasks

        **kwargs1 : dict
            Additional keyword arguments to pass to the `get_kernel`
            function when constructing the base data kernel.

    Returns:
        The constructed multi-task kernel function.
    """

    data_kernel = get_kernel(base_kernel, **kwargs1)

    def multivariate_kernel(X, Z, params, noise=0, **kwargs2):
        """
        Computes multivariate kernel matrix, given two input arrays and
        a dictionary wuth kernel parameters. The input arrays must have the
        shape (N, D) where N is the number of data points and D is the feature
        dimension.
        """

        # Compute data and task kernels
        task_labels = jnp.arange(num_tasks)
        k_data = data_kernel(X, Z, params, 0, **kwargs2)  # noise will be added later
        k_task = index_kernel(task_labels, task_labels, params)

        # Compute the multi-task kernel
        K = jnp.kron(k_data, k_task)

        # Add noise associated with each task
        if X.shape == Z.shape:
            # Make sure noise is a jax ndarray with a proper shape
            if isinstance(noise, (float, int)):
                noise = jnp.ones(num_tasks) * noise
            # Add small jitter for numerical stability
            noise = add_jitter(noise, **kwargs2)
            # Create a block-diagonal noise matrix with the noise terms
            # on the diagonal of each block
            noise_matrix = jnp.kron(jnp.eye(k_data.shape[0]), jnp.diag(noise))
            # Add the noise to the diagonal of the kernel matrix
            K += noise_matrix

        return K

    return multivariate_kernel


def LCMKernel(base_kernel, shared_input_space=True, num_tasks=None, **kwargs1):
    """
    Construct kernel for a Linear Model of Coregionalization (LMC)

    Args:
        base_kernel:
            The name of the data kernel or a function that computes
            the data kernel. This kernel is used to compute the
            similarities in the input space. The built-in kernels are 'RBF',
            'Matern', 'Periodic', and 'NNGP'.
        shared_input_space:
            If True (default), assumes that all tasks share the same input space and
            uses a multivariate kernel (Kronecker product).
            If False, assumes that different tasks have different number of observations
            and uses a multitask kernel (elementwise multiplication). In that case, the task
            indices must be appended as the last column of the input vector.
        num_tasks: int, optional
            Number of tasks. This is only used if `shared_input_space` is True.
        **kwargs1:
            Additional keyword arguments to pass to the `get_kernel`
            function when constructing the base data kernel.

    Returns:
        The constructed LMC kernel function.
    """

    if shared_input_space:
        multi_kernel = MultivariateKernel(base_kernel, num_tasks, **kwargs1)
    else:
        multi_kernel = MultitaskKernel(base_kernel, **kwargs1)

    def lcm_kernel(X, Z, params, noise=0, **kwargs2):
        k = vmap(lambda p: multi_kernel(X, Z, p, noise, **kwargs2))(params)
        return k.sum(0)

    return lcm_kernel


def get_kernel(kernel: Union[str, kernel_fn_type] = 'RBF', **kwargs):
    kernel_book = {
        'RBF': RBFKernel,
        'Matern': MaternKernel,
        'Periodic': PeriodicKernel,
        'NNGP': NNGPKernel(**kwargs)
    }
    if isinstance(kernel, str):
        try:
            kernel = kernel_book[kernel]
        except KeyError:
            print('Select one of the currently available kernels:',
                  *kernel_book.keys())
            raise
    return kernel
