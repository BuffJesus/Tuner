
# Universal Engine Generator Reference Pack

This package contains:

- Engine modeling reference markdown
- Links to authoritative PDFs
- Structured reference material for IDE ingestion

PDF Sources:

1. MIT Internal Combustion Engine Notes
https://ocw.mit.edu/courses/2-61-internal-combustion-engines-spring-2017/

2. Garrett Turbo Tech 103
https://www.garrettmotion.com/wp-content/uploads/2018/06/Turbo-Tech-103.pdf

3. Haltech VE Explanation
https://www.haltech.com/news-events/tuning-with-ve-volumetric-efficiency/

4. Wallace Racing Calculators
https://www.wallaceracing.com/Calculators.htm

These sources were consolidated into the engine_model_reference.md file.

Most relevant findings for the current project:

- boosted modeling should separate engine VE from charge-density effects
- turbo guidance should use pressure ratio, manifold temperature, intercooler effectiveness, and restriction losses explicitly
- generator and autotune logic should be able to identify likely non-VE root causes such as wrong injector flow, deadtime, target-table setup, or MAP/IAT assumptions
