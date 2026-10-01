# Area 47 demo monitoring overview — revision 3

**Document:** DEMO-OPS-047-003 | **Status:** SYNTHETIC TRAINING ONLY — NOT AN OPERATING PROCEDURE

> This guide explains the fictional instruments and trends in the Area 47 demo. All alarm thresholds and instrument ranges are invented. It gives no instructions to adjust equipment, operate valves, bypass interlocks, or perform maintenance. In a real plant use approved alarm response procedures and contact the control room / responsible authority.

## What the scenario monitors

- **Feed and transfer flow:** FT-4711.01 trends liquid flow on the P4711 discharge line. The scenario normal flow is 20 m³/h; 28 m³/h is the illustrative design flow. A low-flow alarm at 12 m³/h is only a demo value.
- **Pump suction and discharge:** PT-4711.01 and PT-4711.02 show suction and discharge pressure. Read these with flow and operating history; one pressure value alone does not establish cavitation or a pump fault.
- **Strainer restriction:** PDI-4702.01 indicates differential pressure across F4702. The demo high alarm is 0.6 bar. A high differential pressure can indicate restriction, but does not authorize basket changeover or opening the strainer.
- **Cooler performance:** TT-1007.01 trends H1007 process outlet temperature. Scenario normal is 35°C, with 55°C inlet. A demo high alarm is 45°C. Utility conditions and approved limits are absent from this fictional data set.
- **Vessel inventory:** LT-4750 provides continuous level indication. T4750 gross capacity is 60 m³; the maximum normal working inventory in this scenario is 48 m³. Demo high alarm is 80% (48 m³), and independent high-high is 90% (54 m³). LALL-4750 is shown at 15% (9 m³).
- **Vessel pressure:** PT-4750 trends vapor-space pressure. The fictional normal target is 2.0 barg. PV4712.02 is the pressure control valve to the closed vapor-recovery header, not a relief valve. PSV-4750.01 is modeled as a separate illustrative relief device to a fictional flare header.
- **Pump condition:** VE-4711.01 records P4711 casing vibration. Demo alert values of 4.5 and 7.1 mm/s RMS are placeholders and are not universal machine limits. Compare actual measurements only with the equipment-specific monitoring program and approved manufacturer/site criteria.

## Example interpretation questions

- If P4711 flow falls while PDI-4702.01 rises, the combination may justify review of strainer differential-pressure trend and operating records by authorized operations staff. It does not prove the strainer is blocked or prescribe a valve changeover.
- If H1007 outlet temperature rises, compare inlet/outlet temperatures, utility-side indications, flow, and recent operating changes using available approved displays. This scenario contains no troubleshooting or adjustment procedure.
- If T4750 level or pressure alarms occur, follow the real site's current alarm response procedure. The values here must never be used as real alarm setpoints.
- Unusual P4711 noise or vibration can have several causes. Record safe observations from an authorized location and escalate under site rules; do not diagnose from sound alone.

## Information to record for a demo trend review

Record timestamp and trend interval, flow, P4711 suction and discharge pressure, F4702 differential pressure, H1007 inlet/outlet temperature, T4750 level and pressure, P4711 vibration, alarm/event identifiers, and relevant process changes. This is a fictional example data checklist, not a site log format or mandatory operator duty.
