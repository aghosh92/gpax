from typing import Callable, Dict, Optional

import jax.numpy as jnp
import numpy as onp
import numpyro
import numpyro.distributions as dist
from numpyro.contrib.module import random_haiku_module

from ..kernels import LCMKernel
from .vidkl import viDKL


class viMTDKL(viDKL):
    def __init__(self, input_dim: int, z_dim: int = 2, data_kernel: str = 'RBF',
                 num_latents: int = None, shared_input_space: bool = True,
                 num_tasks: int = None, rank: Optional[int] = None,
                 data_kernel_prior: Optional[Callable[[], Dict[str, jnp.ndarray]]] = None,
                 nn: Optional[Callable[[jnp.ndarray], jnp.ndarray]] = None,
                 guide: str = 'delta', task_kernel_prior: Optional[Callable[[], Dict[str, jnp.ndarray]]] = None,
                 W_prior_dist: Optional[dist.Distribution] = None,
                 v_prior_dist: Optional[dist.Distribution] = None,
                 **kwargs) -> None:
        args = (input_dim, z_dim, None, None, nn, None, guide)
        super(viMTDKL, self).__init__(*args, **kwargs)
        if shared_input_space:
            if num_tasks is None:
                raise ValueError("Please specify num_tasks")
        else:
            if num_latents is None:
                raise ValueError("Please specify num_latents")
        self.num_tasks = num_tasks
        self.num_latents = num_tasks if num_latents is None else num_latents
        self.rank = rank
        self.kernel = LCMKernel(
            data_kernel, shared_input_space, num_tasks, **kwargs)
        self.data_kernel_prior = data_kernel_prior
        self.task_kernel_prior = task_kernel_prior
        self.shared_input = shared_input_space
        self.W_prior_dist = W_prior_dist
        self.v_prior_dist = v_prior_dist

    def model(self, X: jnp.ndarray, y: jnp.ndarray = None, **kwargs) -> None:
        """Multitask DKL probabilistic model"""

        # Check that we have necessary info for sampling kernel params
        if not self.shared_input and self.num_tasks is None:
            self.num_tasks = len(onp.unique(self.X_train[:, -1]))

        if self.rank is None:
            self.rank = self.num_tasks - 1

        # NN part
        feature_extractor = random_haiku_module(
            "feature_extractor", self.nn_module, input_shape=(1, *self.data_dim),
            prior=(lambda name, shape: dist.Cauchy() if name.startswith("b") else dist.Normal()))
        z = feature_extractor(X if self.shared_input else X[:, :-1])
        if not self.shared_input:
            z = jnp.column_stack((z, X[:, -1]))

        # Initialize GP kernel mean function at zeros
        if self.shared_input:
            f_loc = jnp.zeros(self.num_tasks * X.shape[0])
        else:
            f_loc = jnp.zeros(X.shape[0])

        # Sample data kernel parameters
        if self.data_kernel_prior:
            data_kernel_params = self.data_kernel_prior()
        else:
            data_kernel_params = self._sample_kernel_params()

        # Sample task kernel parameters
        if self.task_kernel_prior:
            task_kernel_params = self.task_kernel_prior()
        else:
            task_kernel_params = self._sample_task_kernel_params()

        # Combine two dictionaries with parameters
        kernel_params = {**data_kernel_params, **task_kernel_params}

        # Sample noise
        if self.noise_prior:  # this will be removed in the future releases
            noise = self.noise_prior()
        else:
            noise = self._sample_noise()

        # Compute multitask_kernel
        k = self.kernel(z, z, kernel_params, noise, **kwargs)

        # Sample y according to the standard Gaussian process formula
        numpyro.sample(
            "y",
            dist.MultivariateNormal(loc=f_loc, covariance_matrix=k),
            obs=y,
        )

    def _sample_noise(self):
        """Sample observational noise"""
        if self.noise_prior_dist is not None:
            noise_dist = self.noise_prior_dist
        else:
            noise_dist = dist.LogNormal(
                    jnp.zeros(self.num_tasks),
                    jnp.ones(self.num_tasks))

        noise = numpyro.sample("noise", noise_dist.to_event(1))
        return noise

    def _sample_task_kernel_params(self):
        """
        Sample task kernel parameters with default weakly-informative priors
        or custom priors for all the latent functions
        """
        if self.W_prior_dist is not None:
            W_dist = self.W_prior_dist
        else:
            W_dist = dist.Normal(
                    jnp.zeros(shape=(self.num_latents, self.num_tasks, self.rank)),  # loc
                    10*jnp.ones(shape=(self.num_latents, self.num_tasks, self.rank)) # var
            )
        if self.v_prior_dist is not None:
            v_dist = self.v_prior_dist
        else:
            v_dist = dist.LogNormal(
                    jnp.zeros(shape=(self.num_latents, self.num_tasks)),  # loc
                    jnp.ones(shape=(self.num_latents, self.num_tasks)) # var
            )
        with numpyro.plate("latent_plate_task", self.num_latents):
            W = numpyro.sample("W", W_dist.to_event(2))
            v = numpyro.sample("v", v_dist.to_event(1))
        return {"W": W, "v": v}

    def _sample_kernel_params(self):
        """
        Sample data ("base") kernel parameters with default weakly-informative
        priors for all the latent functions
        """
        squeezer = lambda x: x.squeeze() if self.num_latents > 1 else x
        with numpyro.plate("latent_plate_data", self.num_latents, dim=-2):
            with numpyro.plate("ard", self.kernel_dim, dim=-1):
                length = numpyro.sample("k_length", dist.LogNormal(0.0, 1.0))
            scale = numpyro.deterministic("k_scale", jnp.ones(self.num_latents))
        return {"k_length": squeezer(length), "k_scale": squeezer(scale)}
