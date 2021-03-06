"""Functions to convert between quantities and fit DCE-MRI data.

Functions:
    sig_to_enh
    enh_to_conc
    conc_to_enh
    conc_to_pkp
    enh_to_pkp
    pkp_to_enh
    volume_fractions
    minimize_global
"""


import numpy as np
from scipy.optimize import root, minimize


def sig_to_enh(s, base_idx):
    """Convert signal data to enhancement.

    Parameters
    ----------
    s : ndarray
        1D float array containing signal time series
    base_idx : list
        list of integers indicating the baseline time points.

    Returns
    -------
    enh : ndarray
        1D float array containing enhancement time series (%)
    """
    s_pre = np.mean(s[base_idx])
    enh = 100.*((s - s_pre)/s_pre)
    return enh


def enh_to_conc(enh, k, R10, c_to_r_model, signal_model):
    """Estimate concentration time series from enhancements.

    Assumptions:
        -fast-water-exchange limit.
        -see conc_to_enh

    Parameters
    ----------
    enh : ndarray
        1D float array containing enhancement time series (%)
    k : float
        B1 correction factor (actual/nominal flip angle)
    R10 : float
        Pre-contrast R1 relaxation rate (s^-1)
    c_to_r_model : c_to_r_model
        Model describing the concentration-relaxation relationship.
    signal_model : signal_model
        Model descriibing the relaxation-signal relationship.

    Returns
    -------
    C_t : ndarray
        1D float array containing tissue concentration time series (mM),
        specifically the mMol of tracer per unit tissue volume.

    """
    # Define function to fit for one time point
    def enh_to_conc_single(e):
        # Find the C where measured-predicted enhancement = 0
        res = root(lambda c:
                   e - conc_to_enh(c, k, R10, c_to_r_model, signal_model),
                   x0=0, method='hybr', options={'maxfev': 1000, 'xtol': 1e-7})
        assert res.success, 'Enh-to-conc root finding failed.'
        return min(res.x)
    # Loop through all time points
    C_t = np.asarray([enh_to_conc_single(e) for e in enh])
    return C_t


def conc_to_enh(C_t, k, R10, c_to_r_model, signal_model):
    """Forward model to convert concentration to enhancement.

    Assumptions:
        -Fast-water-exchange limit.
        -Assumes R20=0 for convenience, which may not be valid for all
        sequences
        -R2* calculation not presently implemented. Assumes R2=R2*

    Parameters
    ----------
    C_t : ndarray
        1D float array containing tissue concentration time series (mM),
        specifically the mMol of tracer per unit tissue volume.
    k : float
        B1 correction factor (actual/nominal flip angle)
    R10 : float
        Pre-contrast R1 relaxation rate (s^-1)
    c_to_r_model : c_to_r_model
        Model describing the concentration-relaxation relationship.
    signal_model : signal_model
        Model descriibing the relaxation-signal relationship.

    Returns
    -------
    enh : ndarray
        1D float array containing enhancement time series (%)
    """
    R1 = c_to_r_model.R1(R10, C_t)
    R2 = c_to_r_model.R2(0, C_t)  # can assume R20=0 for existing signal models
    s_pre = signal_model.R_to_s(s0=1., R1=R10, R2=0, R2s=0, k=k)
    s_post = signal_model.R_to_s(s0=1., R1=R1, R2=R2, R2s=R2, k=k)
    enh = 100. * ((s_post - s_pre) / s_pre)
    return enh


def conc_to_pkp(C_t, pk_model, pk_pars_0=None, weights=None):
    """Fit concentration-time series to obtain pharmacokinetic parameters.

    Uses non-linear least squares optimisation.

    Assumptions:
        -Fast-water-exchange limit
        -See conc_to_enh

    Parameters
    ----------
    C_t : ndarray
        1D float array containing tissue concentration time series (mM),
        specifically the mMol of tracer per unit tissue volume.
    pk_model : pk_model
        Pharmacokinetic model used to predict tracer distribution.
    pk_pars_0 : list, optional
        list of dicts containing starting values of pharmacokinetic parameters.
        If there are >1 dicts then the optimisation will be run multiple times
        and the global minimum used.
        Example: [{'vp': 0.1, 'ps': 1e-3, 've': 0.5}]
        Defaults to values in pk_model.typical_vals.
    weights : ndarray, optional
        1D float array of weightings to use for sum-of-squares calculation.
        Can be used to "exclude" data points from optimisation.
        Defaults to equal weighting for all points.

    Returns
    -------
    tuple (pk_pars_opt, Ct_fit)
        pk_pars_opt : dict of optimal pharmacokinetic parameters,
            Example: {'vp': 0.1, 'ps': 1e-3, 've': 0.5}
        Ct_fit : 1D ndarray of floats containing best-fit tissue
            concentration-time series (mM).
    """
    if pk_pars_0 is None:
        pk_pars_0 = [pk_model.pkp_dict(pk_model.typical_vals)]
    if weights is None:
        weights = np.ones(C_t.shape)

    # Convert initial pars from list of dicts to list of arrays
    x_0_all = [pk_model.pkp_array(pars) for pars in pk_pars_0]
    x_scalefactor = pk_model.typical_vals
    x_0_norm_all = [x_0 / x_scalefactor for x_0 in x_0_all]

    # Define sum-of-squares function to minimise
    def cost(x_norm, *args):
        x = x_norm * x_scalefactor
        C_t_try, _C_cp, _C_e = pk_model.conc(*x)
        ssq = np.sum(weights * ((C_t_try - C_t)**2))
        return ssq

    result = minimize_global(cost, x_0_norm_all, args=None, bounds=None,
                             constraints=pk_model.constraints,
                             method='trust-constr')

    x_opt = result.x * x_scalefactor
    pk_pars_opt = pk_model.pkp_dict(x_opt)  # convert parameters to dict
    Ct_fit, _C_cp, _C_e = pk_model.conc(*x_opt)
    Ct_fit[weights == 0] = np.nan

    return pk_pars_opt, Ct_fit


def enh_to_pkp(enh, hct, k, R10_tissue, R10_blood, pk_model, c_to_r_model,
               water_ex_model, signal_model, pk_pars_0=None, weights=None):
    """Fit signal time series to obtain pharamacokinetic parameters.

    Assumptions:
        -R2 and R2* effects neglected.

    Parameters
    ----------
    enh : ndarray
        1D float array containing enhancement time series (%)
    hct : float
        Capillary haematocrit.
    k : float
        B1 correction factor (actual/nominal flip angle)
    R10_tissue : float
        Pre-contrast R1 relaxation rate for tissue (s^-1)
    R10_blood : float
        Pre-contrast R1 relaxation rate for capillary blood (s^-1). Used to
        estimate R10 for each tissue compartment. AIF R10 value is typically
        used.
    pk_model : TYPE
        DESCRIPTION.
    c_to_r_model : TYPE
        DESCRIPTION.
    water_ex_model : TYPE
        DESCRIPTION.
    signal_model : TYPE
        DESCRIPTION.
    pk_pars_0 : TYPE, optional
        DESCRIPTION. The default is None.
    weights : TYPE, optional
        DESCRIPTION. The default is None.

    Returns
    -------
    TYPE
        DESCRIPTION.

    """
    if pk_pars_0 is None:
        pk_pars_0 = [pk_model.pkp_dict(pk_model.typical_vals)]
    if weights is None:
        weights = np.ones(enh.shape)
        
    x_0_all = [pk_model.pkp_array(pars)  # get starting values as array
           for pars in pk_pars_0]
    x_scalefactor = pk_model.typical_vals
    x_0_norm_all = [x_0 / x_scalefactor for x_0 in x_0_all]
    
    #define function to minimise
    def cost(x_norm, *args):
        x = x_norm * x_scalefactor
        pk_pars_try = pk_model.pkp_dict(x)
        enh_try = pkp_to_enh(pk_pars_try, hct, k, R10_tissue, R10_blood, pk_model, c_to_r_model, water_ex_model, signal_model)
        ssq = np.sum(weights * ((enh_try - enh)**2))    
        return ssq
    
    #perform fitting
    result = minimize_global(cost, x_0_norm_all, args=None,
             bounds=None, constraints=pk_model.constraints, method='trust-constr')

    x_opt = result.x * x_scalefactor
    pk_pars_opt = pk_model.pkp_dict(x_opt)
    enh_fit = pkp_to_enh(pk_pars_opt, hct, k, R10_tissue, R10_blood, pk_model, c_to_r_model, water_ex_model, signal_model)
    enh_fit[weights == 0]=np.nan
    
    return pk_pars_opt, enh_fit


def pkp_to_enh(pk_pars, hct, k, R10_tissue, R10_blood, pk_model, c_to_r_model, water_ex_model, signal_model):   
   
    # volume fractions and spin population fractions
    v = volume_fractions(pk_pars, hct)    
    p = v

    # pre-contrast R10 per compartment
    R10_extravasc = (R10_tissue-p['b']*R10_blood)/(1-p['b'])
    R10 = {'b': R10_blood,
           'e': R10_extravasc,
           'i': R10_extravasc}
    # R10 per compartment --> R1 exponential components 
    R10_components, p0_components = water_ex_model.R1_components(p, R10)
    
    # PK parameters --> tissue compartment concentrations
    C_t, C_cp, C_e = pk_model.conc(**pk_pars)     
    c = { 'b': C_cp / v['b'],
         'e': C_e / v['e'],
         'i': np.zeros(C_e.shape),
         'C_t': C_t }

    # concentration --> R1 per compartment
    R1 = {'b': c_to_r_model.R1(R10['b'], c['b']),
          'e': c_to_r_model.R1(R10['e'], c['e']),
          'i': c_to_r_model.R1(R10['i'], c['i'])}
    
    # R1 per compartment --> R1 exponential components
    R1_components, p_components = water_ex_model.R1_components(p, R1)      
    
    # R1 --> signal enhancement
    s_pre = np.sum([
        p0_c * signal_model.R_to_s(1, R10_components[i], k=k)
        for i, p0_c in enumerate(p0_components)], 0)
    s_post = np.sum([
        p_c * signal_model.R_to_s(1, R1_components[i], k=k)
        for i, p_c in enumerate(p_components)], 0)
    enh = 100. * (s_post - s_pre) / s_pre
    
    return enh


def volume_fractions(pk_pars, hct):
    # if vp exists, calculate vb, otherwise set vb to zero
    if 'vp' in pk_pars:
        vb = pk_pars['vp'] / (1 - hct)
    else:
        vb = 0
    
    # if ve exists define vi as remaining volume, otherwise set to vi zero
    if 've' in pk_pars:
        ve = pk_pars['ve']
        vi = 1 - vb - ve
    else:
        ve = 1 - vb
        vi = 0    
    
    v = {'b': vb, 'e': ve, 'i': vi}
    return v




def minimize_global(cost, x_0_all, **kwargs):
    results = [minimize(cost, x_0, **kwargs) for x_0 in x_0_all]
    costs = [result.fun for result in results]
    cost = min(costs)
    idx = costs.index(cost)
    result = results[idx]
    return result