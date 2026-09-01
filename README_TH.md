# GDS CENTRAL GAME CORE — Phase 8E worktree

> รุ่นที่รับรองแล้วคือ v1.8.5 (Phase 8D) ส่วน worktree ปัจจุบันอยู่ Phase 8E: actor/stamina loop, speech/presentation bridge, critical-home finish-loop, snapshot save/load/replay และเว็บรีวิวภายในทำเสร็จแล้ว เหลือการตรวจรับด้วยสายตา/พฤติกรรมและฝังเข้ากับแอปจริง

> v1.8.5 คือรุ่น **Phase 8D WorkSeat Lifecycle** ที่ต่อยอดจาก Phase 8C Portal Actor Lifecycle โดยคง navigation foundation ที่อนุมัติแล้วของ Phase 8B และเพิ่มวงจรคนเดินเข้าโต๊ะ/นั่งทำงาน/เดินออกแบบ deterministic

สูตร navigation หลักยังเป็น:

`WALKABLE = APPROVED ROOM DOMAIN - ACTIVE OBJECT FOOTPRINTS`

สิ่งที่รวมอยู่ใน v1.8.5:

- `WORLD/RUNTIME/pathfinding_core.py` — deterministic A* แบบ 4-neighbor, cost=1, Manhattan heuristic
- `RUNTIME/character_movement_core.py` — แปลง fine-grid cell center เป็น screen pixel และแมปทิศ `+U=SE`, `-U=NW`, `+V=SW`, `-V=NE`
- ใช้ action `move` / `idle` เดิมของระบบตัวละครเท่านั้น ไม่สร้างภาพ movement ใหม่
- shared ground anchor ของตัวละคร = `[16,31]` บน canvas 32×42
- `CentralGameCore` มี facade สำหรับ pathfinding, portal start, distant target และ character movement
- `RUNTIME/portal_actor_lifecycle.py` — lifecycle `unspawned → entering → active → exiting → despawned`
- ตัวละครแต่ละตัวมี `movement_profile.speed_percent` ฝังถาวรใน metadata (สุ่มชุดใหม่ด้วย speed seed v4) อยู่ในช่วง 225–250%; ทุก spawn/alias/actor seed อ่านค่าเดียวกันและห้าม reroll
- ทุกตัวใช้ tick กลาง 60 ms แต่คำนวณระยะเดินแยกตามสปีดของตัวเอง
- จังหวะภาพเดินอิงระยะทาง โดยขยาย stride เป็น `0.65 × speed` cells เพื่อลดอาการขาปั่นเร็วเกินการเคลื่อนที่
- ทิศทางภาพใช้ lookahead + hysteresis ลดการสลับหันซ้าย/ขวาถี่ ๆ จากเส้น A* แบบขั้นบันได โดยไม่เปลี่ยนเส้นทางจริง
- `RUNTIME/crowd_movement_core.py` ใช้ synchronized continuous trajectory ตรวจเฉพาะระยะหัวตัวละครในเวลาเดียวกันด้วย buffer 2px; รอยทางหรือเส้นทางที่ทับกันคนละเวลาอนุญาตได้, ลองเส้น A* สำรองก่อน และถ้าไม่มีทางอ้อมจะเลื่อนเวลา spawn แบบมองไม่เห็นแทนการให้ตัวที่เกิดแล้วหยุดรอ จึงไม่มี `crowd_wait` หลัง spawn และไม่สลับ actor identity, speed หรือ goal (API reservation แบบเดิมยังเก็บไว้ให้เครื่องมือเก่า)
- `RUNTIME/work_seat_lifecycle.py` — วงจรตัวละครเดี่ยว `walking_to_seat → approach → seated_work → exit_seat → walking_from_seat`; slot ถูก derive จาก navigation/workstation/WorkSeat แบบ capacity-one และใช้ gate เดิม
- action semantics: `idle` = ยืนนิ่งหันคุยตามทิศ, `move` = เดินตามทาง, `work` = นั่งทำงานเท่านั้น, `sad/happy` = อีเวนต์อารมณ์แบบไม่มีทิศ (ใช้สำเร็จ/พลาดนอก work)

สิ่งที่เพิ่มใน Phase 8E worktree:

- `RUNTIME/actor_simulation_core.py` เก็บ stamina แบบ JSON-safe; เมื่อ critical/หมดจะค้างท่า `work/normal_work` ให้จบ loop 720ms แล้วส่ง `home_requested` อัตโนมัติก่อนเดินกลับบ้าน
- standing pair ใช้โบนัสตัวเลข deterministic: `sad -1` และ `happy +2` stamina (ภายใน `-1000/+2000` milli) และ clamp ตามขอบเขต
- ค่า drain/recovery ตอนนี้ติดสถานะ `initial_runtime_tuning_author_review_pending` ยังต้องดู gameplay และให้ผู้เขียนอนุมัติค่าจริงก่อนเรียก final
- `RUNTIME/runtime_persistence.py` และ Central facade มี save/load snapshot กับ deterministic replay จาก step/command ที่ระบุชัดเจน โดยให้แอปภายนอกเป็นเจ้าของ storage
- เปิดเว็บรีวิวด้วย `python TOOLS/runtime_review_server.py` แล้วเข้า `http://127.0.0.1:8765/` เพื่อดู worknormal → critical queue → จบ loop → เดินกลับบ้าน รวมปุ่ม save/load/replay
- Floor00 ผ่าน proof 3 แบบ: near target / distant target / workstation approach และ smoke test ผ่านบน F0/F1/F2/F36
- reception F1 = 16×20 / 320 cells และ F2/F2+ = 34×22 / 748 cells โดยใช้ world ground anchor คงที่ `[259,376]`; depth ของ F1/F2+ ใช้ front edge แยกจากพื้นที่จอง navigation ส่วน F0 ไม่ผูก profile เพราะฝังอยู่ในภาพ
- `TOOLS/grid_floor_editor/index.html` — local editor สำหรับคลิก/คลุมแล้วเปิดหรือปิด Room Grid และ Portal Inside/Outside พร้อม validation และ export patch JSON

กฎ Lean Release ยังเหมือนเดิม:

- เก็บ Room mask canonical แค่ 3 ชุดใน `WORLD/COMPILED_NAV/`
- **ไม่แพ็ก** `WORLD/COMPILED_NAV/OCCUPANCY/`
- **ไม่แพ็ก** `PREVIEW/`, `LOCAL_REVIEW/`, GIF และ QA contact sheet ที่สร้างใหม่ได้
- งานภาพ review ใช้ asset จริง + deterministic compositor เท่านั้น ห้ามใช้โมเดลสร้างภาพ
- WorkSeat runtime takeover แบบ single-actor ลงใน Phase 8D แล้ว; QA ใช้คนเท่าจำนวนคอมของแต่ละ floor แบบหนึ่งคนต่อหนึ่ง workstation จึงไม่มีการแย่ง slot กัน

อ่าน `HANDOFF.md` และ `ROADMAP.md` สำหรับสถานะล่าสุด; การ embed เข้าแอปจริงและ author acceptance ยังเป็น gate ถัดไป
