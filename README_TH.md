# GDS CENTRAL GAME CORE v1.8.4

> สถานะ: **Phase 8C ปิดงานแล้วและผู้เขียนอนุมัติภาพตรวจสอบเมื่อ 2026-08-31**; งานถัดไปคือ Phase 8D WorkSeat runtime lifecycle

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
- ตัวละครแต่ละตัวได้ movement speed แบบสุ่มคงที่หนึ่งครั้งในช่วง 225–250% (สุ่มชุดใหม่ด้วย speed seed v3; เรียกซ้ำได้ค่าเดิม และใส่ actor seed เพิ่มได้)
- ทุกตัวใช้ tick กลาง 60 ms แต่คำนวณระยะเดินแยกตามสปีดของตัวเอง
- จังหวะภาพเดินอิงระยะทาง โดยขยาย stride เป็น `0.65 × speed` cells เพื่อลดอาการขาปั่นเร็วเกินการเคลื่อนที่
- ทิศทางภาพใช้ lookahead + hysteresis ลดการสลับหันซ้าย/ขวาถี่ ๆ จากเส้น A* แบบขั้นบันได โดยไม่เปลี่ยนเส้นทางจริง
- `RUNTIME/crowd_movement_core.py` ใช้ synchronized continuous trajectory ตรวจเฉพาะระยะหัวตัวละครในเวลาเดียวกันด้วย buffer 2px; รอยทางหรือเส้นทางที่ทับกันคนละเวลาอนุญาตได้, ลองเส้น A* สำรองก่อน และถ้าไม่มีทางอ้อมจะเลื่อนเวลา spawn แบบมองไม่เห็นแทนการให้ตัวที่เกิดแล้วหยุดรอ จึงไม่มี `crowd_wait` หลัง spawn และไม่สลับ actor identity, speed หรือ goal (API reservation แบบเดิมยังเก็บไว้ให้เครื่องมือเก่า)
- Floor00 ผ่าน proof 3 แบบ: near target / distant target / workstation approach และ smoke test ผ่านบน F0/F1/F2/F36
- reception F1 = 16×20 / 320 cells และ F2/F2+ = 34×22 / 748 cells โดยใช้ world ground anchor คงที่ `[259,376]`; depth ของ F1/F2+ ใช้ front edge แยกจากพื้นที่จอง navigation ส่วน F0 ไม่ผูก profile เพราะฝังอยู่ในภาพ
- `TOOLS/grid_floor_editor/index.html` — local editor สำหรับคลิก/คลุมแล้วเปิดหรือปิด Room Grid และ Portal Inside/Outside พร้อม validation และ export patch JSON

กฎ Lean Release ยังเหมือนเดิม:

- เก็บ Room mask canonical แค่ 3 ชุดใน `WORLD/COMPILED_NAV/`
- **ไม่แพ็ก** `WORLD/COMPILED_NAV/OCCUPANCY/`
- **ไม่แพ็ก** `PREVIEW/`, `LOCAL_REVIEW/`, GIF และ QA contact sheet ที่สร้างใหม่ได้
- งานภาพ review ใช้ asset จริง + deterministic compositor เท่านั้น ห้ามใช้โมเดลสร้างภาพ
- WorkSeat runtime takeover ยังเป็น Phase 8D; movement timing และ collision avoidance ระหว่างตัวละครมี runtime reservation สำหรับ crowd แล้ว

อ่าน `HANDOFF.md` และรายงานใน `REPORTS/` สำหรับสถานะล่าสุด
