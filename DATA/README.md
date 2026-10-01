# Industrial RAG sample corpus

This is a synthetic demonstration corpus for retrieval, source checking, tag lookup, process-flow questions, and monitoring questions. It is not an operating procedure or an engineering design basis.

- `true_data/` contains the fictional Area 47 scenario associated with example tags such as `P4711`, `H1007`, `T4750`, and `PV4712.02`.
- `true_data/area_47_synthetic_process_design_basis_rev3.md` describes an invented condensate flow path and illustrative equipment capacities.
- `true_data/area_47_process_topology_dexpi_inspired.json` stores a simplified equipment/stream/instrument graph. It is DEXPI-inspired only and is not schema compliant or suitable for engineering software import.
- `true_data/area_47_equipment_datasheets_rev3.csv` and `area_47_instrument_monitoring_register_rev3.csv` provide fictional asset and monitoring data.
- `true_data/area_47_safety_and_work_control_standard_training.md` is a synthetic safety/work-control example for testing legitimate safety questions against safeguard-bypass requests; it is not an approved procedure.
- `noisy_data/` contains distractors, stale examples, and unverified conflicting notes for retrieval evaluation. These must not be treated as authoritative.

The existing `area_47_reference_pid.svg` is a synthetic tag-recognition drawing. The new design basis supplies a separate fictional topology; it does not claim that those connections or values were extracted from the SVG. Every new process value and route is invented for a demo. Real plant work requires controlled, approved documents and qualified engineering review.
