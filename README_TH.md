# GDS CENTRAL GAME CORE v1.8.4

> v1.8.4 คือรุ่น **Phase 8C Portal Actor Lifecycle** โดยคง navigation foundation ที่อนุมัติแล้วของ Phase 8B และเพิ่ม movement แบบต่อเนื่อง, no-redraw walking depth, reception expansion และ lifecycle ของตัวละครที่เข้า/ออกผ่าน portal แบบ deterministic

สูตร navigation หลักยังเป็น:

`WALKABLE = APPROVED ROOM DOMAIN - ACTIVE OBJECT FOOTPRINTS`

สิ่งที่รวมอยู่ใน v1.8.4:

- `WORLD/RUNTIME/pathfinding_core.py` — deterministic A* แบบ 4-neighbor, cost=1, Manhattan heuristic
- `RUNTIME/character_movement_core.py` — แปลง fine-grid cell center เป็น screen pixel และแมปทิศ `+U=SE`, `-U=NW`, `+V=SW`, `-V=NE`
- ใช้ action `move` / `idle` เดิมของระบบตัวละครเท่านั้น ไม่สร้างภาพ movement ใหม่
- shared ground anchor ของตัวละคร = `[16,31]` บน canvas 32×42
- `CentralGameCore` มี facade สำหรับ pathfinding, portal start, distant target และ character movement
- `RUNTIME/portal_actor_lifecycle.py` — lifecycle `unspawned → entering → active → exiting → despawned`
- Floor00 ผ่าน proof 3 แบบ: near target / distant target / workstation approach และ smoke test ผ่านบน F0/F1/F2/F36
- reception F1 = 16×20 / 320 cells และ F2/F2+ = 35×23 / 805 cells โดยใช้ world ground anchor คงที่ `[259,376]`

กฎ Lean Release ยังเหมือนเดิม:

- เก็บ Room mask canonical แค่ 3 ชุดใน `WORLD/COMPILED_NAV/`
- **ไม่แพ็ก** `WORLD/COMPILED_NAV/OCCUPANCY/`
- **ไม่แพ็ก** `PREVIEW/`, GIF และ QA contact sheet ที่สร้างใหม่ได้
- งานภาพ review ใช้ asset จริง + deterministic compositor เท่านั้น ห้ามใช้โมเดลสร้างภาพ
- WorkSeat runtime takeover เป็น Phase 8D และ multi-character runtime จะทำภายหลัง

อ่าน `HANDOFF.md` และรายงานใน `REPORTS/` สำหรับสถานะล่าสุด
