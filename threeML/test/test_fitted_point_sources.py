import pytest
from threeML import *
from threeML.plugins.OGIPLike import OGIPLike
from threeML.utils.fitted_objects.fitted_point_sources import InvalidUnitError
import itertools

def make_simple_model():
    triggerName = 'bn090217206'
    ra = 204.9
    dec = -8.4
    datadir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../examples'))
    obsSpectrum = os.path.join(datadir, "bn090217206_n6_srcspectra.pha{1}")
    bakSpectrum = os.path.join(datadir, "bn090217206_n6_bkgspectra.bak{1}")
    rspFile = os.path.join(datadir, "bn090217206_n6_weightedrsp.rsp{1}")
    NaI6 = OGIPLike("NaI6", obsSpectrum, bakSpectrum, rspFile)
    NaI6.set_active_measurements("10.0-30.0", "40.0-950.0")
    data_list = DataList(NaI6)
    powerlaw = Powerlaw()
    GRB = PointSource(triggerName, ra, dec, spectral_shape=powerlaw)
    model = Model(GRB)

    powerlaw.index.prior = Uniform_prior(lower_bound=-5.0, upper_bound=5.0)
    powerlaw.K.prior = Log_uniform_prior(lower_bound=1.0, upper_bound=10)



    return model, data_list


def make_componets_model():

    triggerName = 'bn090217206'
    ra = 204.9
    dec = -8.4
    datadir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../examples'))
    obsSpectrum = os.path.join(datadir, "bn090217206_n6_srcspectra.pha{1}")
    bakSpectrum = os.path.join(datadir, "bn090217206_n6_bkgspectra.bak{1}")
    rspFile = os.path.join(datadir, "bn090217206_n6_weightedrsp.rsp{1}")
    NaI6 = OGIPLike("NaI6", obsSpectrum, bakSpectrum, rspFile)
    NaI6.set_active_measurements("10.0-30.0", "40.0-950.0")
    data_list = DataList(NaI6)
    powerlaw = Powerlaw() + Blackbody()
    GRB = PointSource(triggerName, ra, dec, spectral_shape=powerlaw)
    model = Model(GRB)

    powerlaw.index_1.prior = Uniform_prior(lower_bound=-5.0, upper_bound=5.0)
    powerlaw.K_1.prior = Log_uniform_prior(lower_bound=1.0, upper_bound=10)

    powerlaw.K_2.prior = Uniform_prior(lower_bound=-5.0, upper_bound=5.0)
    powerlaw.kT_2.prior = Log_uniform_prior(lower_bound=1.0, upper_bound=10)

    return model, data_list

simple_model, simple_data = make_simple_model()

complex_model, complex_data = make_componets_model()
# prepare mle


jl_simple = JointLikelihood(simple_model,simple_data)

jl_simple.fit()

jl_complex = JointLikelihood(complex_model,complex_data)

jl_complex.fit()


bayes_simple = BayesianAnalysis(simple_model, simple_data)

bayes_simple.sample(10,10,20)

bayes_complex = BayesianAnalysis(complex_model, complex_data)


bayes_complex.sample(10,10,20)


good_d_flux_units =['1/(cm2 s keV)', 'erg/(cm2 s keV)', 'erg2/(cm2 s keV)']

good_i_flux_units =['1/(cm2 s )', 'erg/(cm2 s )', 'erg2/(cm2 s )']


good_energy_units = ['keV', 'Hz', 'nm']


bad_flux_units = ['g']


analysis_to_test = [jl_simple,jl_complex,bayes_simple,bayes_complex]


flux_keywords = {'use_components': True,
                 'components_to_use': ['total','Powerlaw'],
                 'sources_to_use':['bn090217206'],
                 'flux_unit':'erg/(cm2 s)',
                 'energy_unit':'keV'}

plot_keywords = {'use_components': True,
                 'components_to_use': ['Powerlaw','total'],
                 'sources_to_use':['bn090217206'],
                 'flux_unit':'erg/(cm2 s)',
                 'energy_unit':'keV',
                 'plot_style_kwargs':{},
                 'contour_style_kwargs':{},
                 'legend_kwargs':{},
                 'ene_min':10,
                 'ene_max':100,
                 'show_legend':False,
                 'fit_cmap':'jet',
                 'countor_cmap':'jet'}


def test_fitted_point_source_plotting():


    for u1, u2 in zip(good_d_flux_units,good_i_flux_units):

        for e_unit in good_energy_units:

            print u

            for x in itertools.product(analysis_to_test):

                calculate_point_source_flux(1,10,*x,flux_unit=u2,energy_unit=e_unit)

                calculate_point_source_flux(1, 10, *x, ** flux_keywords)

                plot_point_source_spectra(*x,flux_unit=u1,energy_unit=e_unit)

                plot_point_source_spectra(*x,**plot_keywords)

                with pytest.raises(InvalidUnitError):

                    calculate_point_source_flux(0,10,*x,flux_unit=bad_flux_units[0])

                with pytest.raises(InvalidUnitError):
                    plot_point_source_spectra(*x,flux_unit=bad_flux_units[0])

