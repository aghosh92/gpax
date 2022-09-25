GPax: Structured Gaussian Processes and Deep Kernel Learning
============================================================

GPax is a small Python package for physics-based Gaussian processes (GPs) built on top of NumPyro and JAX. Its purpose is to take advantage of prior physical knowledge and different data modalities when using GPs for data reconstruction and active learning. It is a work in progress, and more models will be added in the near future.

.. image:: imgs/GPax.jpg
  :alt: GPax

.. toctree::
   :maxdepth: 3
   :caption: Notes

   README.rst
   LICENSE.rst
   USAGE.rst

.. toctree::
   :maxdepth: 3
   :caption: Package Content

   models
   acquisition
   kernels
   utils

.. toctree::
   :maxdepth: 3
   :caption: Examples

   examples 