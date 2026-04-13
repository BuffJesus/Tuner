# Universal Engine Performance Modeling Reference
Version: 2.0  
Purpose: Universal tuning software generator reference

This document defines formulas, assumptions, and modeling logic for:

- VE Table Generation
- AFR Table Generation
- Spark Table Estimation
- Turbo Modeling
- Camshaft Modeling
- Injector Sizing
- Torque / HP Estimation

Sources Combined:

- MIT Internal Combustion Engine Notes
- Garrett Turbo Tech 103
- Haltech VE Documentation
- Wallace Racing Calculators
- Speed Density Modeling
- MegaSquirt / Speeduino principles

---

# SECTION 1 — Core Speed Density Model

Speed Density determines airflow using:

Air Mass = Air Density × Displacement × VE

Expanded:

Air Mass = (MAP × VE × Displacement) / (R × Temperature)

Where:

MAP = Manifold absolute pressure
VE = volumetric efficiency
R = Gas constant
Temperature = Intake air temp (Kelvin)

---

# SECTION 2 — Engine Airflow Formula

CFM = (CID × RPM × VE) / 3456

Variables:

CID = displacement in cubic inches
RPM = engine speed
VE = volumetric efficiency

---

# SECTION 3 — Convert CFM to Mass Airflow

lb/min = CFM / 14.27

This enables:

- Turbo sizing
- Injector sizing
- HP estimation

---

# SECTION 4 — Horsepower Estimation

Naturally aspirated:

HP ≈ lb/min × 9.5

Turbocharged:

HP ≈ lb/min × 10

Aggressive turbo:

HP ≈ lb/min × 10.5

---

# SECTION 5 — Torque Estimation

Torque:

Torque = (HP × 5252) / RPM

Or estimate directly:

Torque ≈ Displacement × BMEP / 150.8

Typical BMEP:

NA engine:

120-180 psi

Turbo engine:

180-260 psi

---

# SECTION 6 — Pressure Ratio

Pressure Ratio:

PR = (Boost + Atmospheric) / Atmospheric

Atmospheric:

14.7 psi

Example:

8 psi boost

PR = (8 + 14.7) / 14.7

PR = 1.54

---

# SECTION 7 — Boosted Airflow

Boost multiplies airflow:

Boosted airflow:

Airflow × Pressure Ratio

---

# SECTION 8 — Air Density Correction

Air density:

Density ∝ Pressure / Temperature

Hot air:

Less density

Cold air:

More density

Temperature correction:

Corrected airflow:

Airflow × (Standard Temp / Actual Temp)

Standard temp:

293K (20°C)

---

# SECTION 9 — Volumetric Efficiency Ranges

Stock engines:

60-85%

Performance:

80-100%

Turbo engines:

75-100%

Race engines:

95-115%

---

# SECTION 10 — Camshaft Influence

Important Cam Specs:

Duration @ .050  
LSA  
Lift  
Overlap  
Intake closing

---

# SECTION 11 — Duration Effects

Short duration:

Better low RPM

Long duration:

Better high RPM

Typical:

180-200 mild  
200-215 mild performance  
215-230 performance  
230+ aggressive

---

# SECTION 12 — LSA Effects

108-110:

Aggressive

112-114:

Performance

114-116:

Turbo friendly

---

# SECTION 13 — Overlap Effects

More overlap:

Better high RPM

Less overlap:

Better turbo spool

---

# SECTION 14 — Head Flow Multiplier

Stock:

1.00

Mild port:

1.03

Performance:

1.05

Race:

1.10+

---

# SECTION 15 — Turbo Efficiency

Small turbo:

1.00-1.05

Large turbo:

0.95-1.00

Twin turbo:

1.02-1.08

---

# SECTION 16 — Turbo Spool Model

Boost vs RPM curve

Example:

RPM | Boost
2000 | 2 psi
2500 | 5 psi
3000 | 8 psi

---

# SECTION 17 — Exhaust Backpressure

Backpressure reduces VE

Small turbo:

Higher backpressure

Large turbo:

Lower backpressure

Multiplier:

0.95-1.00

---

# SECTION 18 — Dynamic Compression

Depends on:

Intake closing  
Rod ratio  
Stroke

Late intake close:

Lower compression

Early intake close:

Higher compression

---

# SECTION 19 — Fuel Type Modeling

Fuel Types:

Gasoline:

Stoich 14.7

E85:

Stoich 9.8

Methanol:

Stoich 6.4

---

# SECTION 20 — AFR Targets

Turbo:

Idle:

14.2

Cruise:

14.7

Boost:

11.5-12.0

NA:

Idle:

14.2

Cruise:

14.7

WOT:

12.5-13.0

---

# SECTION 21 — Injector Sizing

Injector:

HP × BSFC / (Injectors × Duty)

BSFC:

NA:

0.45-0.50

Turbo:

0.55-0.65

---

# SECTION 22 — Injector Deadtime

Important for:

Idle accuracy

Required:

Deadtime  
Voltage compensation

---

# SECTION 23 — VE Table Shape

RPM | VE
800 | 45
1200 | 55
1600 | 65
2000 | 75
2500 | 82
3000 | 88
3500 | 90
4000 | 89
4500 | 87
5000 | 84

---

# SECTION 24 — Spark Table Estimation

Low load:

30-45°

Boost:

15-25°

Idle:

10-18°

---

# SECTION 25 — Mechanical Loss

Typical:

12-20%

Large engines:

Higher loss

---

# SECTION 26 — Generator Inputs

Displacement  
Cylinders  
Cam specs  
Compression ratio  
Boost  
Turbo type  
Head type  
Fuel type  
Injector size  
RPM range

---

# SECTION 27 — Generator Outputs

VE table  
AFR table  
Spark table  
Torque curve  
HP estimate  
Injector recommendation

---

# SECTION 28 — Advanced Modeling

Sequential turbo  
Compound turbo  
Twin charging  
Variable cam timing  
Intercooler efficiency

---

# SECTION 29 — Intercooler Efficiency

Typical:

No intercooler:

0%

Small intercooler:

50-60%

Good intercooler:

70-80%

Excellent:

80-90%

---

# SECTION 30 — Example Engine

Ford 300 twin turbo

300 CID

8 psi

VE:

0.88

Airflow:

331 CFM

Boosted:

510 CFM

HP:

350-380

---

# SECTION 31 — Future Expansion

Machine learning tuning  
Compressor map parsing  
Dyno correction  
Altitude correction

---

# SECTION 32 — Project Implications

Most useful implementation takeaways for this repo:

- do not treat boost as a direct VE multiplier
- model charge density and engine VE separately
- use pressure ratio, manifold temperature, intercooler effectiveness, and restriction losses explicitly for boosted airflow reasoning
- keep generator and autotune conclusions deterministic, reviewable, and able to say when the problem is probably not VE itself

Generator improvements suggested by this reference pack:

- add a charge-density layer distinct from base VE shape for boosted engines
- estimate compressor operating points from pressure ratio plus mass flow, then surface surge/choke/confidence notes
- cross-check horsepower target, BSFC range, AFR target, injector count, and duty-cycle assumptions together
- allow torque-peak-informed VE shaping when the operator has credible airflow or torque context
- make altitude, atmospheric pressure, inlet restriction, and intercooler assumptions explicit in summaries

Autotune improvements suggested by this reference pack:

- flag likely non-VE root causes such as wrong injector flow, deadtime, engine displacement, MAP/IAT assumptions, or AFR target setup
- apply stronger confidence penalties in boosted spool-transition regions and in low pulsewidth / deadtime-dominated areas
- distinguish likely airflow-model error, transient-fueling error, target-table error, and sensor-model error in the review surface

These references strengthen deterministic modeling and reviewable diagnostics first. They do not justify replacing staged correction logic with opaque ML behavior.

---

END DOCUMENT
