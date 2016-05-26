import collections
import os
import warnings

import astropy.io.fits as pyfits
import numpy
import scipy.integrate

from threeML.minimizer import minimization
from threeML.plugin_prototype import PluginPrototype
from threeML.plugins.gammaln import logfactorial
from threeML.plugins.ogip import OGIPPHA
from threeML.plugins.FermiGBMLike import FermiGBMLike
from astromodels.parameter import Parameter

__instrument_name = "Fermi GBM (all detectors)"


class FermiGBMLike(FermiGBMLike):
    def __init__(self, name, ttefile, bkgselections, rspfile):
        '''
        If the input files are TTE files. Background selections are specified as
        a nested list/array e.g. [[-10,0],[10,20]]
        
        FermiGBMLike("GBM","glg_tte_n6_bn080916412.fit",[[-10,0][10,20]],"rspfile.rsp{2}")
        to load the second spectrum, second background spectrum and second response.
        '''

        self.name = name
        self._backgroundselections = bkgselections
        self._backgroundexists = False
        # Check that all file exists
        notExistant = []

        if (not os.path.exists(ttefile):
            notExistant.append(ttefile)


        if (not os.path.exists(rspfile.split("{")[0])):
            notExistant.append(rspfile.split("{")[0])

        if (len(notExistant) > 0):

            for nt in notExistant:
                print("File %s does not exists!" % (nt))

            raise IOError("One or more input file do not exist!")

        self.phafile = OGIPPHA(phafile, filetype='observed')
        self.exposure = self.phafile.getExposure()
        self.bkgfile = OGIPPHA(bkgfile, filetype="background")
        self.response = Response(rspfile)

        # Start with an empty mask (the user will overwrite it using the
        # setActiveMeasurement method)
        self.mask = numpy.asarray(
            numpy.ones(self.phafile.getRates().shape),
            numpy.bool)

        # Get the counts for this spectrum
        self.counts = (self.phafile.getRates()[self.mask]
                       * self.exposure)

        # Check that counts is positive
        idx = (self.counts < 0)

        if (numpy.sum(idx) > 0):
            warnings.warn("The observed spectrum for %s " % self.name +
                          "has negative channels! Fixing those to zero.",
                          RuntimeWarning)
            self.counts[idx] = 0

        pass

        # Get the background counts for this spectrum
        self.bkgCounts = (self.bkgfile.getRates()[self.mask]
                          * self.exposure)

        # Check that bkgCounts is positive
        idx = (self.bkgCounts < 0)

        if (numpy.sum(idx) > 0):
            warnings.warn("The background spectrum for %s " % self.name +
                          "has negative channels! Fixing those to zero.",
                          RuntimeWarning)
            self.bkgCounts[idx] = 0

        # Check that the observed counts are positive

        idx = self.counts < 0

        if numpy.sum(idx) > 0:
            raise RuntimeError("Negative counts in observed spectrum %s. Data are corrupted." % (phafile))

        # Keep a copy which will never be modified
        self.counts_backup = numpy.array(self.counts, copy=True)
        self.bkgCounts_backup = numpy.array(self.bkgCounts, copy=True)

        # Effective area correction is disabled by default, i.e.,
        # the nuisance parameter is fixed to 1
        self.nuisanceParameters = {}
        self.nuisanceParameters['InterCalib'] = Parameter("InterCalib", 1, min_value=0.9, max_value=1.1, delta=0.01)
        self.nuisanceParameters['InterCalib'].fix = True

    pass

    def _fitGlobalAndDetermineOptimumGrade(self,cnts,bins):
        #Fit the sum of all the channels to determine the optimal polynomial
        #grade
        Nintervals                = len(bins)

       

        #y                         = []
        #for i in range(Nintervals):
        #  y.append(numpy.sum(counts[i]))
        #pass
        #y                         = numpy.array(y)

        #exposure                  = numpy.array(data.field("EXPOSURE"))

        print("\nLooking for optimal polynomial grade:")
        #Fit all the polynomials
        minGrade                  = 0
        maxGrade                  = 4
        logLikelihoods            = []
        for grade in range(minGrade,maxGrade+1):      
          polynomial, logLike     = self._polyfit(bins,cnts,grade)
          logLikelihoods.append(logLike)         
        pass
        #Found the best one
        deltaLoglike              = array(map(lambda x:2*(x[0]-x[1]),zip(logLikelihoods[:-1],logLikelihoods[1:])))
        print("\ndelta log-likelihoods:")
        for i in range(maxGrade):
          print("%s -> %s: delta Log-likelihood = %s" %(i,i+1,deltaLoglike[i]))
        pass
        print("") 
        deltaThreshold            = 9.0
        mask                      = (deltaLoglike >= deltaThreshold)
        if(len(mask.nonzero()[0])==0):
          #best grade is zero!
          bestGrade               = 0
        else:  
          bestGrade                 = mask.nonzero()[0][-1]+1
        pass

       

        return bestGrade
    
    def _FitBackground(self):

        self._backgroundexists = True
        ## Seperate everything by energy channel
        
        
        eneLcs = []

        #eMax = self.chanLU['E_MAX']
        #eMin = self.chanLU['E_MIN']
        #chanWidth = eMax - eMin

        # Select all the events that are in the background regions
        # and make a mask

        allbkgmasks = []
        for bkgsel in self._backgroundselections:
            allbkgmasks.append(numpy.logical_and(self.ttefile.evts-self.phafile.triggertime>= bkgsel[0],
                                                  self.ttefile.evts-self.phafile.triggertime<= bkgsel[1] ))
        backgroundmask = allbkgmasks[0]
        # If there are multiple masks:
        if len(allbkgmasks>1):
            for mask in allbkgmasks[1:]:
                backgroundmask = numpy.logical_or(backgroundmask,mask)

        # Now we will find the the best poly order unless the use specidied one
        # The total cnts (over channels) is binned to 1 sec intervals
        totalbkgevents = self.ttefile.evts[backgroundmask]
        binwidth=1.
        cnts,bins=numpy.histogram(totalbkgevents-self.ttefile.triggertime,
                                  bins=numpy.arange(self.ttefile.startevents-self.ttefile.triggertime,
                                                    self.ttefile.stopevents-self.ttefile.triggertime,
                                                    binwidth))

        cnts=cnts/binwidth
        # Find the mean time of the bins
        meantime=[]
        for i in xrange(len(bins)-1):
            m = mean((bins[i],bins[i+1]))
            meantime.append(m)
        meantime = nump.array(meantime)

        # Remove bins with zero counts
        allnonzeromask = []
        for bkgsel in self._backgroundselections:              
            nonzeromask.append(numpy.logical_and(meantime>= bkgsel[0],
                                                 meantime<= bkgsel[1] ))
        
        nonzeromask = allnonzeromask[0]
        if len(allnonzeromask)>1:
            for mask in allnonzeromask[1:]:
                nonzeromask=numpy.logical_or(mask,nonzeromask)

        self.optimalPolGrade = self._fitGlobalAndDetermineOptimumGrade(cnts[nonzeromask],meantime[nonzeromask])
                
        polynomials = []                                                      
        for chan in range(self.ttefile.nchans):

            # index all events for this channel and select them
            channelmask = self.ttefile.pha == chan
            #channelselectedevents = self.ttefile.events[channelmask]
            # Mask background events and current channel
            bkgchanmask = numpy.logical_and(backgroundmask,channelmask)
            # Select the masked events
            currentevents = self.ttefile.events[bkgchanmask]


        #    eneLcs.append(evts)
        #self.eneLcs = eneLcs
        #self.bkgCoeff = []

        #polynomials               = []

      
        #for elc,cw in zip(eneLcs,chanWidth):
            # Now bin the selected events into 1 second bins
            binwidth=1.
            cnts,bins=numpy.histogram(currentevents-self.ttefile.triggertime,
                                      bins=numpy.arange(self.ttefile.startevents-self.ttefile.triggertime,
                                                        self.ttefile.stopevents-self.ttefile.triggertime,
                                                        binwidth))

            cnts=cnts/binwidth

            # Find the mean time of the bins
            meantime=[]
            for i in xrange(len(bins)-1):
                m = mean((bins[i],bins[i+1]))
                meantime.append(m)
            meantime = nump.array(meantime)

            # Remove bins with zero counts
            allnonzeromask = []
            for bkgsel in self._backgroundselections:              
                nonzeromask.append(numpy.logical_and(meantime>= bkgsel[0],
                                                      meantime<= bkgsel[1] ))
        
            nonzeromask = allnonzeromask[0]
            if len(allnonzeromask)>1:
                for mask in allnonzeromask[1:]:
                    nonzeromask=numpy.logical_or(mask,nonzeromask)


            # Finally, we fit the background and add the polynomial to a list
            thispolynomial,cstat    = self._fitChannel(cnts[nonzeromask],meantime[nonzeromask], self.optimalPolGrade)      
            polynomials.append(thisPolynomial)

        self._polynomials = polynomials


    def _fitChannel(self,cnts,bins,polGrade):

        Nintervals                = len(bins)
        #Put data to fit in an x vector and y vector
        
        polynomial, minLogLike    = self._polyfit(bins,cnts,polGrade)

        return polynomial, minLogLike
        
    def _polyfit(self,x,y,polGrade):

        test = False

        #Check that we have enough counts to perform the fit, otherwise
        #return a "zero polynomial"
        nonzeroMask               = ( y > 0 )
        Nnonzero                  = len(nonzeroMask.nonzero()[0])
        if(Nnonzero==0):
          #No data, nothing to do!
          return Polynomial([0.0]), 0.0
        pass  

        #Compute an initial guess for the polynomial parameters,
        #with a least-square fit (with weight=1) using SVD (extremely robust):
        #(note that polyfit returns the coefficient starting from the maximum grade,
        #thus we need to reverse the order)
        if(test):
          print("  Initial estimate with SVD..."),
        with warnings.catch_warnings():
          warnings.simplefilter("ignore")
          initialGuess            = numpy.polyfit(x,y,polGrade)
        pass
        initialGuess              = initialGuess[::-1]
        if(test):
          print("  done -> %s" %(initialGuess))


        polynomial                = Polynomial(initialGuess)

        #Check that the solution found is meaningful (i.e., definite positive 
        #in the interval of interest)
        M                         = polynomial(x)
        negativeMask              = (M < 0)
        if(len(negativeMask.nonzero()[0])>0):
          #Least square fit failed to converge to a meaningful solution
          #Reset the initialGuess to reasonable value
          initialGuess[0]         = mean(y)
          meanx                   = mean(x)
          initialGuess            = map(lambda x:abs(x[1])/pow(meanx,x[0]),enumerate(initialGuess))

        #Improve the solution using a logLikelihood statistic (Cash statistic)
        logLikelihood             = BkgLogLikelihood(x,y,polynomial)        

        #Check that we have enough non-empty bins to fit this grade of polynomial,
        #otherwise lower the grade
        dof                       = Nnonzero-(polGrade+1)      
        if(test): 
          print("Effective dof: %s" %(dof))
        if(dof <= 2):
          #Fit is poorly or ill-conditioned, have to reduce the number of parameters
          while(dof < 2 and len(initialGuess)>1):
            initialGuess          = initialGuess[:-1]
            polynomial            = Polynomial(initialGuess)
            logLikelihood         = BkgLogLikelihood(x,y,polynomial)  
          pass        
        pass

        #Try to improve the fit with the log-likelihood    
        #try:
        if(1==1):
          finalEstimate           = scipy.optimize.fmin(logLikelihood, initialGuess, 
                                                        ftol=1E-5, xtol=1E-5,
                                                        maxiter=1e6,maxfun=1E6,
                                                        disp=False)
        #except:
        else:
          #We shouldn't get here!
          raise RuntimeError("Fit failed! Try to reduce the degree of the polynomial.")
        pass

        #Get the value for cstat at the minimum
        minlogLikelihood          = logLikelihood(finalEstimate)

        #Update the polynomial with the fitted parameters,
        #and the relative covariance matrix
        finalPolynomial           = Polynomial(finalEstimate)
        try:
          finalPolynomial.computeCovarianceMatrix(logLikelihood.getFreeDerivs)             
        except Exception:
          raise
        #if test is defined, compare the results with those obtained with ROOT
      

        return finalPolynomial, minlogLikelihood
        pass



    
    def useIntercalibrationConst(self, factorLowBound=0.9, factorHiBound=1.1):
        self.nuisanceParameters['InterCalib'].free()
        self.nuisanceParameters['InterCalib'].set_bounds(factorLowBound, factorHiBound)

        # Check that the parameter is within the provided bounds
        value = self.nuisanceParameters['InterCalib'].value

        if (value < factorLowBound):
            warnings.warn(
                "The intercalibration constant was %s, lower than the provided lower bound %s." % (value, factorLowBound) +
                " Setting it equal to the lower bound")

            self.nuisanceParameters['InterCalib'].setValue(float(factorLowBound))

        if (value > factorHiBound):
            warnings.warn(
                "The intercalibration constant was %s, larger than the provided hi bound %s." % (value, factorHiBound) +
                " Setting it equal to the hi bound")

            self.nuisanceParameters['InterCalib'].setValue(float(factorHiBound))















            
    def fixIntercalibrationConst(self, value=None):

        if (value is not None):
            # Fixing the constant to the provided value
            self.nuisanceParameters['InterCalib'].value = float(value)

        else:

            # Do nothing, i.e., leave the constant to the value
            # it currently has
            pass

        self.nuisanceParameters['InterCalib'].fix()

    def setActiveMeasurements(self, *args):
        '''Set the measurements to be used during the analysis.
        Use as many ranges as you need,
        specified as 'emin-emax'. Energies are in keV. Example:

        setActiveMeasurements('10-12.5','56.0-100.0')

        which will set the energy range 10-12.5 keV and 56-100 keV to be
        used in the analysis'''

        # To implelemnt this we will use an array of boolean index,
        # which will filter
        # out the non-used channels during the logLike

        # Now build the mask: values for which the mask is 0 will be masked
        mask = numpy.zeros(self.phafile.getRates().shape)

        for arg in args:
            ee = map(float, arg.replace(" ", "").split("-"))
            emin, emax = sorted(ee)
            idx1 = self.response.energyToChannel(emin)
            idx2 = self.response.energyToChannel(emax)
            mask[idx1:idx2 + 1] = True
        pass
        self.mask = numpy.array(mask, numpy.bool)

        self.counts = self.counts_backup[self.mask]
        self.bkgCounts = self.bkgCounts_backup[self.mask]

        print("Now using %s channels out of %s" % (numpy.sum(self.mask),
                                                   self.phafile.getRates().shape[0]
                                                   ))

    pass

    def get_name(self):
        '''
        Return a name for this dataset (likely set during the constructor)
        '''
        return self.name

    pass

    def set_model(self, likelihoodModel):
        '''
        Set the model to be used in the joint minimization.
        '''
        self.likelihoodModel = likelihoodModel

        nPointSources = self.likelihoodModel.get_number_of_point_sources()

        # This is a wrapper which iterates over all the point sources and get
        # the fluxes
        # We assume there are no extended sources, since the GBM cannot handle them

        def diffFlux(energies):
            fluxes = self.likelihoodModel.get_point_source_fluxes(0, energies)

            # If we have only one point source, this will never be executed
            for i in range(1, nPointSources):
                fluxes += self.likelihoodModel.get_point_source_fluxes(i, energies)

            return fluxes

        self.diffFlux = diffFlux

        # The following integrates the diffFlux function using Simpson's rule
        # This assume that the intervals e1,e2 are all small, which is guaranteed
        # for any reasonable response matrix, given that e1 and e2 are Monte-Carlo
        # energies. It also assumes that the function is smooth in the interval
        # e1 - e2 and twice-differentiable, again reasonable on small intervals for
        # decent models. It might fail for models with too sharp features, smaller
        # than the size of the monte carlo interval.

        def integral(e1, e2):
            # Simpson's rule

            return (e2 - e1) / 6.0 * (self.diffFlux(e1)
                                      + 4 * self.diffFlux((e1 + e2) / 2.0)
                                      + self.diffFlux(e2))

        self.response.setFunction(diffFlux,
                                  integral)

    pass

    def inner_fit(self):

        # Effective area correction
        if (self.nuisanceParameters['InterCalib'].free):

            # A true fit would be an overkill, and slow
            # Just sample a 100 values and choose the minimum
            values = numpy.linspace(self.nuisanceParameters['InterCalib'].min_value,
                                    self.nuisanceParameters['InterCalib'].max_value,
                                    100)

            # I do not use getLogLike so I can compute only once the folded model
            # (which is not going to change during the inner fit)

            folded = self.getFoldedModel()

            modelCounts = folded * self.exposure

            def fitfun(cons):

                self.nuisanceParameters['InterCalib'].value = cons

                return (-1) * self._computeLogLike(
                    self.nuisanceParameters['InterCalib'].value * modelCounts + self.bkgCounts)

            logLval = map(fitfun, values)
            idx = numpy.argmax(logLval)
            self.nuisanceParameters['InterCalib'].value = values[idx]
            # return logLval[idx]

            # Now refine with minuit

            parameters = collections.OrderedDict()
            parameters[(self.name, 'InterCalib')] = self.nuisanceParameters['InterCalib']
            minimizer = minimization.MinuitMinimizer(fitfun, parameters)
            bestFit, mlogLmin = minimizer.minimize()

            return mlogLmin * (-1)

        else:

            return self.get_log_like()

    def getFoldedModel(self):

        # Get the folded model for this spectrum
        # (this is the rate predicted, in cts/s)

        return self.response.convolve()[self.mask]

    def getModelAndData(self):

        e1, e2 = (self.response.ebounds[:, 0],
                  self.response.ebounds[:, 1])

        return (self.response.convolve()[self.mask] * self.exposure
                + self.bkgCounts,
                e1[self.mask],
                e2[self.mask],
                self.counts)

    def _getModelCounts(self):

        # Get the folded model for this spectrum (this is the rate predicted,
        # in cts/s)

        folded = self.getFoldedModel()

        # Model is folded+background (i.e., we assume negligible errors on the
        # background)
        modelCounts = self.nuisanceParameters['InterCalib'].value * folded * self.exposure + self.bkgCounts

        return modelCounts

    def _computeLogLike(self, modelCounts):

        return numpy.sum(- modelCounts
                         + self.counts * numpy.log(modelCounts)
                         - logfactorial(self.counts))

    def get_log_like(self):
        '''
        Return the value of the log-likelihood with the current values for the
        parameters
        '''

        modelCounts = self._getModelCounts()

        logLike = self._computeLogLike(modelCounts)

        return logLike

    def get_nuisance_parameters(self):
        '''
        Return a list of nuisance parameter names. Return an empty list if there
        are no nuisance parameters
        '''
        return self.nuisanceParameters.keys()

    pass


pass

class GBMTTEFile(object):

    def __init__(ttefile):

        tte = pyfits.open(ttefile)
        
        self.events = tte['EVENTS'].data['TIME']
        self.pha = tte['EVENTS'].data['PHA']
        self.triggertime = tte['PRIMARY'].header['TRIGTIME']
        self.startevents = tte['PRIMARY'].header['TSTART']
        self.stopevents = tte['PRIMARY'].header['TSTOP']
        self.nchans = tte['EBOUNDS']['NAXIS2']



class BkgLogLikelihood(object):
  '''
  Implements a Poisson likelihood (i.e., the Cash statistic). Mind that this is not
  the Castor statistic (Cstat). The difference between the two is a constant given
  a dataset. I kept Cash instead of Castor to make easier the comparison with ROOT
  during tests, since ROOT implements the Cash statistic.
  '''
  def __init__(self,x,y,model,**kwargs):
    self.x                    = x
    self.y                    = y
    self.model                = model
    self.parameters           = model.getParams()
    
    #Initialize the exposure to 1.0 (i.e., non-influential)
    #It will be replaced by the real exposure if the exposure keyword
    #have been used
    self.exposure             = numpy.zeros(len(x))+1.0
        
    for key in kwargs.keys():
      if  (key.lower()=="exposure"):            
        self.exposure = numpy.array(kwargs[key])
    pass  
        
  pass
  
  def _evalLogM(self,M):
    #Evaluate the logarithm with protection for negative or small
    #numbers, using a smooth linear extrapolation (better than just a sharp
    #cutoff)
    tiny                      = numpy.float64(numpy.finfo(M[0]).tiny)
    
    nontinyMask               = (M > 2.0*tiny)
    tinyMask                  = numpy.logical_not(nontinyMask)
    
    if(len(tinyMask.nonzero()[0])>0):      
      logM                     = numpy.zeros(len(M))
      logM[tinyMask]           = numpy.abs(M[tinyMask])/tiny + log(tiny) -1
      logM[nontinyMask]        = log(M[nontinyMask])
    else:
      logM                     = log(M)
    return logM
  pass
  
  def __call__(self, parameters):
    '''
      Evaluate the Cash statistic for the given set of parameters
    '''
    
    #Compute the values for the model given this set of parameters
    self.model.setParams(parameters)
    M                         = self.model(self.x)*self.exposure
    Mfixed,tiny               = self._fixPrecision(M)
    
    #Replace negative values for the model (impossible in the Poisson context)
    #with zero
    negativeMask              = (M < 0)
    if(len(negativeMask.nonzero()[0])>0):
      M[negativeMask]         = 0.0
    pass
    
    #Poisson loglikelihood statistic (Cash) is:
    # L = Sum ( M_i - D_i * log(M_i))   
    
    logM                      = self._evalLogM(M)
    
    #Evaluate v_i = D_i * log(M_i): if D_i = 0 then the product is zero
    #whatever value has log(M_i). Thus, initialize the whole vector v = {v_i}
    #to zero, then overwrite the elements corresponding to D_i > 0
    d_times_logM              = numpy.zeros(len(self.y))
    nonzeroMask               = (self.y > 0)
    d_times_logM[nonzeroMask] = self.y[nonzeroMask] * logM[nonzeroMask]
    
    logLikelihood             = numpy.sum( Mfixed - d_times_logM )

    return logLikelihood    
  pass
  
  def _fixPrecision(self,v):
    '''
      Round extremely small number inside v to the smallest usable
      number of the type corresponding to v. This is to avoid warnings
      and errors like underflows or overflows in math operations.
    '''
    tiny                      = numpy.float64(numpy.finfo(v[0]).tiny)
    zeroMask                  = (numpy.abs(v) <= tiny)
    if(len(zeroMask.nonzero()[0])>0):
      v[zeroMask]               = numpy.sign(v[zeroMask])*tiny
    
    return v, tiny
  pass
  
  def getFreeDerivs(self,parameters=None):
    '''
    Return the gradient of the logLikelihood for a given set of parameters (or the current
    defined one, if parameters=None)
    '''
    #The derivative of the logLikelihood statistic respect to parameter p is:
    # dC / dp = Sum [ (dM/dp)_i - D_i/M_i (dM/dp)_i]
    
    #Get the number of parameters and initialize the gradient to 0
    Nfree                     = self.model.getNumFreeParams()
    derivs                    = numpy.zeros(Nfree)
    
    #Set the parameters, if a new set has been provided
    if(parameters!=None):
      self.model.setParams(parameters)
    pass
    
    #Get the gradient of the model respect to the parameters
    modelDerivs               = self.model.getFreeDerivs(self.x)*self.exposure
    #Get the model
    M                         = self.model(self.x)*self.exposure
    
    M, tinyM                  = self._fixPrecision(M)
    
    #Compute y_divided_M = y/M: inizialize y_divided_M to zero
    #and then overwrite the elements for which y > 0. This is to avoid
    #possible underflow and overflow due to the finite precision of the
    #computer
    y_divided_M               = numpy.zeros(len(self.y))
    nonzero                   = (self.y > 0)
    y_divided_M[nonzero]      = self.y[nonzero]/M[nonzero]
       
    for p in range(Nfree):
      thisModelDerivs, tinyMd = self._fixPrecision(modelDerivs[p])
      derivs[p]               = numpy.sum(thisModelDerivs * (1.0 - y_divided_M) )
    pass
    
    return derivs
    
  pass
    
pass

class Polynomial(object):
  def __init__(self,params):
    self.params               = params
    self.degree               = len(params)-1
    
    #Build an empty covariance matrix
    self.covMatrix            = numpy.zeros([self.degree+1,self.degree+1])
  pass
  
  def horner(self, x):
    """A function that implements the Horner Scheme for evaluating a
    polynomial of coefficients *args in x."""
    result = 0
    for coefficient in self.params[::-1]:
        result = result * x + coefficient
    return result
  pass
  
  def __call__(self,x):
    return self.horner(x)
  pass
  
  def __str__(self):        
    #This is call by the print() command
    #Print results
    output                    = "\n------------------------------------------------------------"
    output                   += '\n| {0:^10} | {1:^20} | {2:^20} |'.format("COEFF","VALUE","ERROR")
    output                   += "\n|-----------------------------------------------------------"
    for i,parValue in enumerate(self.getParams()):
      output                 += '\n| {0:<10d} | {1:20.5g} | {2:20.5g} |'.format(i,parValue,math.sqrt(self.covMatrix[i,i]))
    pass
    output                   += "\n------------------------------------------------------------"
    
    return output
  pass
  
  def setParams(self,parameters):
    self.params               = parameters
  pass

  def getParams(self):
    return self.params
  pass
  
  def getNumFreeParams(self):
    return self.degree+1
  pass
  
  def getFreeDerivs(self,x):
    Npar                      = self.degree+1
    freeDerivs                = []
    for i in range(Npar):
      freeDerivs.append(map(lambda xx:pow(xx,i),x))
    pass
    return numpy.array(freeDerivs)
  pass
  
  def computeCovarianceMatrix(self,statisticGradient):
    self.covMatrix            = computeCovarianceMatrix(statisticGradient,self.params)
    #Check that the covariance matrix is positive-defined
    negativeElements          = (numpy.matrix.diagonal(self.covMatrix) < 0)
    if(len(negativeElements.nonzero()[0]) > 0):
      raise RuntimeError("Negative element in the diagonal of the covariance matrix. Try to reduce the polynomial grade.")
  pass  
  
  def getCovarianceMatrix(self):
    return self.covMatrix
  pass
  
  def integral(self,xmin,xmax):
    '''
    Evaluate the integral of the polynomial between xmin and xmax
    '''
    integralCoeff             = [0]
    integralCoeff.extend(map(lambda i:self.params[i-1]/float(i),range(1,self.degree+1+1)))
    
    integralPolynomial        = Polynomial(integralCoeff)
    
    return integralPolynomial(xmax) - integralPolynomial(xmin)
  pass
  
  def integralError(self,xmin,xmax):
    # Based on http://root.cern.ch/root/html/tutorials/fit/ErrorIntegral.C.html
    
    #Set the weights
    i_plus_1                  = numpy.array(range(1,self.degree+1+1),'d')
    def evalBasis(x):
      return (1/i_plus_1) * pow(x,i_plus_1)
    c                         = evalBasis(xmax) - evalBasis(xmin)
    
    #Compute the error on the integral
    err2                      = 0.0
    nPar                      = self.degree+1
    parCov                    = self.getCovarianceMatrix()
    for i in range(nPar):
      s                       = 0.0
      for j in range(nPar):
        s                    += parCov[i,j] * c[j]
      pass
      err2                   += c[i]*s
    pass
    
    return math.sqrt(err2)
  pass
  
pass

def computeCovarianceMatrix(grad,par,full_output=False,
          init_step=0.01,min_step=1e-12,max_step=1,max_iters=50,
          target=0.1,min_func=1e-7,max_func=4):
          
    """Perform finite differences on the _analytic_ gradient provided by user to calculate hessian/covariance matrix.

    Positional args:
        grad                : a function to return a gradient
        par                 : vector of parameters (should be function minimum for covariance matrix calculation)

    Keyword args:

        full_output [False] : if True, return information about convergence, else just the covariance matrix
        init_step   [1e-3]  : initial step size (0.04 ~ 10% in log10 space); can be a scalar or vector
        min_step    [1e-6]  : the minimum step size to take in parameter space
        max_step    [1]     : the maximum step size to take in parameter sapce
        max_iters   [5]     : maximum number of iterations to attempt to converge on a good step size
        target      [0.5]   : the target change in the function value for step size
        min_func    [1e-4]  : the minimum allowable change in (abs) function value to accept for convergence
        max_func    [4]     : the maximum allowable change in (abs) function value to accept for convergence
    """

    nparams                   = len(par)
    step_size                 = numpy.ones(nparams)*init_step
    step_size                 = numpy.maximum(step_size,min_step*1.1)
    step_size                 = numpy.minimum(step_size,max_step*0.9)
    hess                      = numpy.zeros([nparams,nparams])
    min_flags                 = numpy.asarray([False]*nparams)
    max_flags                 = numpy.asarray([False]*nparams)

    def revised_step(delta_f,current_step,index):
        if (current_step == max_step):
            max_flags[i]      = True
            return True,0
        
        elif (current_step == min_step):
            min_flags[i]      = True
            return True,0
        
        else:
            adf               = abs(delta_f)
            if adf < 1e-8:
                # need to address a step size that results in a likelihood change that's too
                # small compared to precision
                pass
                
            if (adf < min_func) or (adf > max_func):
                new_step      = current_step/(adf/target)
                new_step      = min(new_step,max_step)
                new_step      = max(new_step,min_step)
                return False,new_step
            else:
                return True,0
    
    iters                     = numpy.zeros(nparams)
    for i in xrange(nparams):
        converged             = False
        
        for j in xrange(max_iters):        
            iters[i]         += 1
            
            di                = step_size[i]
            par[i]           += di
            g_up              = grad(par)
            
            par[i]           -= 2*di
            g_dn              = grad(par)
            
            par[i]           += di
            
            delta_f           = (g_up - g_dn)[i]
            
            converged,new_step = revised_step(delta_f,di,i)
            #print 'Parameter %d -- Iteration %d -- Step size: %.2e -- delta: %.2e'%(i,j,di,delta_f)
            
            if converged: 
              break
            else: 
              step_size[i] = new_step
        pass
        
        hess[i,:] = (g_up - g_dn) / (2*di)  # central difference
        
        if not converged:
            print 'Warning: step size for parameter %d (%.2g) did not result in convergence.'%(i,di)
    try:
        cov = numpy.linalg.inv(hess)
    except:
        print 'Error inverting hessian.'
        raise Exception('Error inverting hessian')
    if full_output:
        return cov,hess,step_size,iters,min_flags,max_flags
    else:
        return cov
    pass
pass

