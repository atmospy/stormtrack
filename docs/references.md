# References

Primary sources for the formats, definitions and conventions used in `imdtrack`. Only
works that were consulted are listed.

**Data and formats**

- Knapp, K. R., M. C. Kruk, D. H. Levinson, H. J. Diamond, and C. J. Neumann, 2010: The
  International Best Track Archive for Climate Stewardship (IBTrACS): Unifying tropical
  cyclone best track data. *Bull. Amer. Meteor. Soc.*, **91**, 363–376,
  doi:10.1175/2009BAMS2755.1.
- Sampson, C. R., and A. J. Schrader, 2000: The Automated Tropical Cyclone Forecasting
  System (version 3.2). *Bull. Amer. Meteor. Soc.*, **81**, 1231–1240,
  doi:10.1175/1520-0477(2000)081<1231:TATCFS>2.3.CO;2. (ATCF deck format.)
- Landsea, C. W., and J. L. Franklin, 2013: Atlantic hurricane database uncertainty and
  presentation of a new database format. *Mon. Wea. Rev.*, **141**, 3576–3592,
  doi:10.1175/MWR-D-12-00254.1. (HURDAT2 and best-track uncertainty.)

**Methods**

- Kaplan, J., and M. DeMaria, 2003: Large-scale characteristics of rapidly intensifying
  tropical cyclones in the North Atlantic basin. *Wea. Forecasting*, **18**, 1093–1108,
  doi:10.1175/1520-0434(2003)018<1093:LCORIT>2.0.CO;2. (Rapid intensification, ≈ 30 kt in
  24 h, used by `analysis.rapid_intensification`.)
- Harper, B. A., J. D. Kepert, and J. D. Ginger, 2010: *Guidelines for converting between
  various wind averaging periods in tropical cyclone conditions.* WMO/TD-No. 1555.
  (Table 1.2: `Vmax600 = K·Vmax60`, K = 0.93 at sea; used by `analysis.convert_vmax`. The
  guidelines give no factor for 3-minute winds.)

**Agency documentation (not peer-reviewed)**

- NHC, *Definition of the NHC Track Forecast Cone*, <https://www.nhc.noaa.gov/aboutcone.shtml>.
- NHC, *Forecast Verification*, <https://www.nhc.noaa.gov/verification/verify4.shtml>.
- India Meteorological Department, RSMC New Delhi, intensity grades and the best-track
  workbook, <https://rsmcnewdelhi.imd.gov.in/> (`analysis.grade_from_wind`).

**Not cited on purpose**: accumulated cyclone energy (`analysis.ace`) follows the common
operational definition (10⁻⁴ Σ v², v ≥ 34 kt, 6-hourly); a primary paper for it has not
been verified, so none is cited here.
