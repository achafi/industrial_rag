# Area 47 synthetic condensate handling process — design basis revision 3

**Document:** DEMO-PFD-047-003 | **Revision:** 3 | **Status:** SYNTHETIC TRAINING SCENARIO — NOT FOR DESIGN, PROCUREMENT, CONSTRUCTION, OPERATION, OR MAINTENANCE

> Every service description, connection, line number, capacity, operating value, alarm, and setpoint below is invented for a software demonstration. This is not an approved DEXPI deliverable, P&ID, process design, operating envelope, or safe-work instruction. It does not amend or reinterpret `area_47_reference_pid.svg`. Use controlled plant engineering documents for real decisions.

## Purpose and process overview

This fictional Area 47 example represents a small stabilized-hydrocarbon-condensate transfer and buffer system. The process starts at upstream battery-limit connection **BL-47-IN**, where a fictional upstream stabilization section supplies condensate. The fluid enters **V4701**, a small inlet separator, then its liquid outlet passes through **F4702**, a duplex basket strainer, **P4711**, a transfer pump, and **H1007**, a cooler, before entering **T4750**, a closed buffer/storage vessel.

The normal liquid outlet of T4750 feeds **P4751**, a downstream transfer pump, and leaves Area 47 at **BL-47-OUT** to a fictional export header. T4750 vapor space connects through pressure-control valve **PV4712.02** to the closed vapor-recovery battery limit **BL-47-VR**. PV4712.02 is a control valve in this invented example; it is not a pressure safety valve. A separate illustrative relief device, **PSV-4750.01**, protects the vessel and discharges to the fictional closed flare header **BL-47-FLARE**.

### Normal liquid path

`BL-47-IN → V4701 → F4702 → P4711 → H1007 → T4750 → P4751 → BL-47-OUT`

1. Stabilized condensate enters V4701 at the Area 47 inlet battery limit.
2. V4701 separates entrained gas from liquid. Gas leaves the vessel overhead to the fictional low-pressure vapor-recovery header; liquid leaves its bottom outlet.
3. Liquid passes through F4702. The duplex arrangement is shown only as a design concept; no field changeover instructions are provided.
4. P4711 transfers liquid through H1007. H1007 cools the stream using a fictional cooling-water utility.
5. Cooled liquid enters T4750 for temporary buffer storage.
6. P4751 transfers liquid from T4750 to the export battery limit BL-47-OUT.

### Vapor and relief connections

- V4701 overhead: line **47-G-4701-2** to **BL-47-VR**.
- T4750 vapor outlet: line **47-G-4750-2**, through **PV4712.02**, to **BL-47-VR**. The illustrative pressure controller maintains T4750 near 2.0 barg by manipulating this valve.
- T4750 relief connection: **PSV-4750.01** to line **47-G-4750-3** and **BL-47-FLARE**. Do not confuse PSV-4750.01 with PV4712.02.
- This package defines conceptual connectivity for the fictional scenario only. It does not establish real isolation boundaries, valve lineups, or permission to perform work.

## Illustrative design data

- Fluid: fictional stabilized hydrocarbon condensate; composition, vapor pressure, and hazardous properties are not specified.
- Normal liquid throughput: **20 m³/h**; scenario design throughput: **28 m³/h**.
- V4701: **40 m³ gross liquid volume**; normal liquid inventory **8–20 m³**.
- F4702: duplex strainer, illustrative **250 µm** basket rating; design flow **28 m³/h**.
- P4711: centrifugal transfer pump, rated **28 m³/h at 55 m differential head**, illustrative 15 kW motor; normal flow **20 m³/h**.
- H1007: shell-and-tube cooler, illustrative normal duty **220 kW**, design duty **280 kW**; condensate temperature **55°C inlet / 35°C outlet** at the scenario normal case.
- T4750: vertical closed buffer vessel, **60 m³ gross capacity** and **48 m³ maximum normal working inventory**. Typical inventory is **20–36 m³**. The scenario uses **10 barg design pressure**, **2.0 barg normal pressure**, design temperature **−10 to 80°C**, and normal liquid temperature **25–40°C**.
- P4751: centrifugal export pump, rated **28 m³/h at 45 m differential head**, illustrative 15 kW motor; normal transfer **20 m³/h**.
- All stated figures are fictional demonstration values, not calculations or recommendations. The complete illustrative values are tabulated in `area_47_equipment_datasheets_rev3.csv`.

## Monitoring concept

The fictional instrumentation package includes inlet flow indication **FT-4711.01**, P4711 suction/discharge pressure **PT-4711.01/PT-4711.02**, H1007 outlet temperature **TT-1007.01**, T4750 level **LT-4750**, T4750 vapor pressure **PT-4750**, pump vibration **VE-4711.01**, and pressure control valve **PV4712.02**. Illustrative alarms and functions are in `area_47_instrument_monitoring_register_rev3.csv`.

The operator-facing monitoring overview is in `area_47_operator_monitoring_guide_rev3.md`. Its checks describe what the demo instruments represent; they are not alarm response steps. Actual alarms, trips, interlocks, calibration intervals, and operating limits require approved control narratives, cause-and-effect charts, instrument datasheets, and site procedures.

## DEXPI note and evidence boundary

`area_47_process_topology_dexpi_inspired.json` records equipment, stream, and instrument relationships in a small DEXPI-inspired graph for RAG demonstrations. It is **not a DEXPI-compliant XML exchange file**, does not implement a DEXPI profile, and must not be imported into engineering software as a plant model. The original reference SVG contains tag examples; this supplemental synthetic scenario is the sole source for the invented connections and values above.
