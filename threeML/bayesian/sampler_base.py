import numpy as np
import abc
import collections
import math
from future.utils import with_metaclass


try:

    # see if we have mpi and/or are using parallel

    from mpi4py import MPI

    if MPI.COMM_WORLD.Get_size() > 1:  # need parallel capabilities
        using_mpi = True

        comm = MPI.COMM_WORLD
        rank = comm.Get_rank()

    else:

        using_mpi = False
except:

    using_mpi = False


from threeML.analysis_results import BayesianResults
from threeML.utils.statistics.stats_tools import aic, bic, dic
from threeML.exceptions.custom_exceptions import LikelihoodIsInfinite, custom_warnings
from astromodels.functions.function import ModelAssertionViolation


class SamplerBase(with_metaclass(abc.ABCMeta, object)):
    def __init__(self, likelihood_model=None, data_list=None, **kwargs):
        """

        The base class for all bayesian samplers. Provides a common interface
        to access samples and byproducts of fits. 


        :param likelihood_model: the likelihood model
        :param data_list: the data list 
        :returns: 
        :rtype: 

        """

        self._samples = None
        self._raw_samples = None
        self._sampler = None
        self._log_like_values = None
        self._log_probability_values = None
        self._results = None
        self._is_setup = False
        self._is_registered = False

        if (likelihood_model is not None) and (data_list is not None):

            self._register_model_and_data(likelihood_model, data_list)

    def set_model_and_data(self, likelihood_model, data_list):
        """

        set the likelihood model and data list after instantiation

        :param likelihood_model: the likelihood model
        :param data_list: the data list
        :returns: 
        :rtype: 

        """

        self._register_model_and_data(likelihood_model, data_list)

    def _register_model_and_data(self, likelihood_model, data_list):
        """

        make sure the model and data list are set up

        :param likelihood_model: 
        :param data_list: 
        :returns: 
        :rtype: 

        """

        # Verify that all the free parameters have priors
        for parameter_name, parameter in likelihood_model.free_parameters.items():

            if not parameter.has_prior():
                raise RuntimeError(
                    "You need to define priors for all free parameters before instancing a "
                    "Bayesian analysis"
                )

        # Process optional keyword parameters

        self._verbose = False

        self._likelihood_model = likelihood_model

        self._data_list = data_list

        for dataset in list(self._data_list.values()):

            dataset.set_model(self._likelihood_model)

            # Now get the nuisance parameters from the data and add them to the model
            # NOTE: it is important that this is *after* the setting of the model, as some
            # plugins might need to adjust the number of nuisance parameters depending on the
            # likelihood model

            for parameter_name, parameter in list(dataset.nuisance_parameters.items()):
                # Enforce that the nuisance parameter contains the instance name, because otherwise multiple instance
                # of the same plugin will overwrite each other's nuisance parameters

                assert dataset.name in parameter_name, (
                    "This is a bug of the plugin for %s: nuisance parameters "
                    "must contain the instance name" % type(dataset)
                )

                self._likelihood_model.add_external_parameter(parameter)

        self._is_registered = True

    @abc.abstractmethod
    def setup(self):
        pass

    @abc.abstractmethod
    def sample(self):
        pass

    @property
    def results(self):

        return self._results

    @property
    def samples(self):
        """
        Access the samples from the posterior distribution generated by the selected sampler

        :return: a dictionary with the samples from the posterior distribution for each parameter
        """
        return self._samples

    @property
    def raw_samples(self):
        """
        Access the samples from the posterior distribution generated by the selected sampler in raw form (i.e.,
        in the format returned by the sampler)

        :return: the samples as returned by the sampler
        """

        return self._raw_samples

    @property
    def log_like_values(self):
        """
        Returns the value of the log_likelihood found by the bayesian sampler while samplin  g from the posterior. If
        you need to find the values of the parameters which generated a given value of the log. likelihood, remember
        that the samples accessible through the property .raw_samples are ordered in the same way as the vector
        returned by this method.

        :return: a vector of log. like values
        """
        return self._log_like_values

    @property
    def log_probability_values(self):
        """
        Returns the value of the log_probability (posterior) found by the bayesian sampler while sampling from the posterior. If
        you need to find the values of the parameters which generated a given value of the log. likelihood, remember
        that the samples accessible through the property .raw_samples are ordered in the same way as the vector
        returned by this method.

        :return: a vector of log probabilty values
        """

        return self._log_probability_values

    @property
    def log_marginal_likelihood(self):
        """
        Return the log marginal likelihood (evidence) if computed
        :return:
        """

        return self._marginal_likelihood

    def restore_median_fit(self):
        """
        Sets the model parameters to the mean of the marginal distributions
        """

        for i, (parameter_name, parameter) in enumerate(self._free_parameters.items()):
            # Add the samples for this parameter for this source

            mean_par = np.median(self._samples[parameter_name])
            parameter.value = mean_par

    def _build_samples_dictionary(self):
        """
        Build the dictionary to access easily the samples by parameter

        :return: none
        """

        self._samples = collections.OrderedDict()

        for i, (parameter_name, parameter) in enumerate(self._free_parameters.items()):
            # Add the samples for this parameter for this source

            self._samples[parameter_name] = self._raw_samples[:, i]

    def _build_results(self):
        """
        build the results after a fit is performed

        :returns: 
        :rtype: 

        """

        # Find maximum of the log posterior
        idx = self._log_probability_values.argmax()

        # Get parameter values at the maximum
        approximate_MAP_point = self._raw_samples[idx, :]

        # Sets the values of the parameters to their MAP values
        for i, parameter in enumerate(self._free_parameters):

            self._free_parameters[parameter].value = approximate_MAP_point[i]

        # Get the value of the posterior for each dataset at the MAP
        log_posteriors = collections.OrderedDict()

        log_prior = self._log_prior(approximate_MAP_point)

        # keep track of the total number of data points
        # and the total posterior

        total_n_data_points = 0

        total_log_posterior = 0

        for dataset in list(self._data_list.values()):

            log_posterior = dataset.get_log_like() + log_prior

            log_posteriors[dataset.name] = log_posterior

            total_n_data_points += dataset.get_number_of_data_points()

            total_log_posterior += log_posterior

        # compute the statistical measures

        statistical_measures = collections.OrderedDict()

        # compute the point estimates

        statistical_measures["AIC"] = aic(
            total_log_posterior, len(self._free_parameters), total_n_data_points
        )
        statistical_measures["BIC"] = bic(
            total_log_posterior, len(self._free_parameters), total_n_data_points
        )

        this_dic, pdic = dic(self)

        # compute the posterior estimates

        statistical_measures["DIC"] = this_dic
        statistical_measures["PDIC"] = pdic

        if self._marginal_likelihood is not None:

            statistical_measures["log(Z)"] = self._marginal_likelihood

        # TODO: add WAIC

        # Instance the result

        self._results = BayesianResults(
            self._likelihood_model,
            self._raw_samples,
            log_posteriors,
            statistical_measures=statistical_measures,
        )

    def _update_free_parameters(self):
        """
        Update the dictionary of the current free parameters
        :return:
        """

        self._free_parameters = self._likelihood_model.free_parameters

    def get_posterior(self, trial_values):
        """Compute the posterior for the normal sampler"""

        # Assign this trial values to the parameters and
        # store the corresponding values for the priors

        # self._update_free_parameters()

        assert len(self._free_parameters) == len(trial_values), (
            "Something is wrong. Number of free parameters "
            "do not match the number of trial values."
        )

        log_prior = 0

        # with use_

        for i, (parameter_name, parameter) in enumerate(self._free_parameters.items()):

            prior_value = parameter.prior(trial_values[i])

            if prior_value == 0:
                # Outside allowed region of parameter space

                return -np.inf

            else:

                parameter.value = trial_values[i]

                log_prior += math.log10(prior_value)

        log_like = self._log_like(trial_values)

        # print("Log like is %s, log_prior is %s, for trial values %s" % (log_like, log_prior,trial_values))

        return log_like + log_prior

    def _log_prior(self, trial_values):
        """Compute the sum of log-priors, used in the parallel tempering sampling"""

        # Compute the sum of the log-priors

        log_prior = 0

        for i, (parameter_name, parameter) in enumerate(self._free_parameters.items()):

            prior_value = parameter.prior(trial_values[i])

            if prior_value == 0:
                # Outside allowed region of parameter space

                return -np.inf

            else:

                parameter.value = trial_values[i]

                log_prior += math.log10(prior_value)

        return log_prior

    def _log_like(self, trial_values):
        """Compute the log-likelihood"""

        # Get the value of the log-likelihood for this parameters

        try:

            # Loop over each dataset and get the likelihood values for each set

            log_like_values = [
                dataset.get_log_like() for dataset in list(self._data_list.values())
            ]

        except ModelAssertionViolation:

            # Fit engine or sampler outside of allowed zone

            return -np.inf

        except:

            # We don't want to catch more serious issues

            raise

        # Sum the values of the log-like

        log_like = np.sum(log_like_values)

        if not np.isfinite(log_like):
            # Issue warning

            custom_warnings.warn(
                "Likelihood value is infinite for parameters %s" % trial_values,
                LikelihoodIsInfinite,
            )

            return -np.inf

        return log_like


class MCMCSampler(SamplerBase):
    def __init__(self, likelihood_model, data_list, **kwargs):

        super(MCMCSampler, self).__init__(likelihood_model, data_list, **kwargs)

    def _get_starting_points(self, n_walkers, variance=0.1):

        # Generate the starting points for the walkers by getting random
        # values for the parameters close to the current value

        # Fractional variance for randomization

        # (0.1 means var = 0.1 * value )
        p0 = []

        for i in range(n_walkers):
            this_p0 = [
                x.get_randomized_value(variance)
                for x in list(self._free_parameters.values())
            ]

            p0.append(this_p0)

        return p0


class UnitCubeSampler(SamplerBase):
    def __init__(self, likelihood_model, data_list, **kwargs):

        super(UnitCubeSampler, self).__init__(likelihood_model, data_list, **kwargs)

    def _construct_unitcube_posterior(self, return_copy=False):
        """

        Here, we construct the prior and log. likelihood for multinest etc on the unit cube
        """

        # First update the free parameters (in case the user changed them after the construction of the class)
        self._update_free_parameters()

        def loglike(trial_values, ndim=None, params=None):

            # NOTE: the _log_like function DOES NOT assign trial_values to the parameters

            for i, parameter in enumerate(self._free_parameters.values()):
                parameter.value = trial_values[i]

            log_like = self._log_like(trial_values)

            if self._verbose:
                n_par = len(self._free_parameters)

                print(
                    "Trial values %s gave a log_like of %s"
                    % (["%.2g" % trial_values[i] for i in range(n_par)], log_like)
                )

            return log_like

        # Now construct the prior
        # MULTINEST priors are defined on the unit cube
        # and should return the value in the bounds... not the
        # probability. Therefore, we must make some transforms

        if return_copy:

            def prior(cube):
                params = cube.copy()

                for i, (parameter_name, parameter) in enumerate(
                    self._free_parameters.items()
                ):

                    try:

                        params[i] = parameter.prior.from_unit_cube(params[i])

                    except AttributeError:

                        raise RuntimeError(
                            "The prior you are trying to use for parameter %s is "
                            "not compatible with sampling from a unitcube"
                            % parameter_name
                        )
                return params

        else:

            def prior(params, ndim=None, nparams=None):

                for i, (parameter_name, parameter) in enumerate(
                    self._free_parameters.items()
                ):

                    try:

                        params[i] = parameter.prior.from_unit_cube(params[i])

                    except AttributeError:

                        raise RuntimeError(
                            "The prior you are trying to use for parameter %s is "
                            "not compatible with sampling from a unitcube"
                            % parameter_name
                        )

            # Give a test run to the prior to check that it is working. If it crashes while multinest is going
            # it will not stop multinest from running and generate thousands of exceptions (argh!)
            n_dim = len(self._free_parameters)

            _ = prior([0.5] * n_dim, n_dim, [])

        return loglike, prior
