# Python code for fitting DCE-MRI data
Note: this repository is a work-in-progress, un-tested and not recommended for use.

### Functionality:
- Signal-to-concentration
- Fit concentration using pharmacokinetic model
- Fit signal using pharmacokinetic model
- Pharmacokinetic models: steady-state, Patlak
- Individual and Parker AIFs
- Linear relaxivity model
- SPGR signal model
- Water exchange models: FXL, NXL, NXL_be

### Not yet implemented/limitations:
- Untested!
- Written for flexibility, not speed
- Other pharmacokinetic models (add by inheriting pk_model class)
- Non-linear relaxivity models add by inheriting c_to_r_model class)
- Other population AIFs (add by inheriting aif class)
- Other water exchange models, e.g. 3S2X, 2S1X (add by inheriting water_ex_model class)
- Signal models for other sequences (add by inheriting signal_model class)
- Model constraints
- Time-shifting AIFs
- Fitting a time delay
- Fitting water exchange parameters
- Raising exceptions e.g. for non-physical values
- Finding global minimum
- "Special" implementations, e.g. linear(ised) pharmacokinetic models

### To do list (short-term):
- fit enhancement not signal(?)
- aif shifts (to allow pre-contrast data points in sims)
- normalise y fitting variable
- create demo notebooks
- finish T1 fitting
- search for global minimum
- optimise tolerances, iterations etc.
- documentation and comments
- exceptions
- testing
