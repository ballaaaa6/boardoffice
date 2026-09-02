# Editable dialogue catalog and bubble presentation

คลังใช้งานจริงอยู่ที่ [dialogue.csv](<D:/antigravity/board office/CHARACTER/DIALOGUE/dialogue.csv>).
แก้ข้อความ เพิ่มคำพูด เพิ่มคำแปล หรือเปลี่ยนหมวดได้ที่ไฟล์นี้ โดยไม่ต้องแก้ renderer หรือไฟล์ใน 00_STARTING_POINT/ และไม่ต้องนำเข้าทับจาก LOCAL_REVIEW อีก

ณ การนำเข้าแรก 2026-08-31: 204 phrase IDs × 2 ภาษา = 408 แถว พร้อม hello_world_test/en เดิมอีก 1 แถว รวม 409 แถว. หลังผู้ใช้อนุมัติร่างขยาย ได้เติมอีก 800 phrase IDs × 2 ภาษา = 1,600 แถว ทำให้ปัจจุบันมี 1,005 IDs / 2,009 แถว. แถว `office` เปิดใช้แล้วครบ 1,872 แถว (รวม test row ที่เปิดใช้อีก 1 แถว); แถว context-only/template/future ยังคงปิดตาม scope และไม่ถูกเลือกเป็นบทพูดออฟฟิศ

รายงานการเติมครั้งนี้อยู่ที่ [import_report.json](<D:/antigravity/board office/LOCAL_REVIEW/DIALOGUE_CATALOG_IMPORT_20260831/import_report.json>) พร้อมสำเนา CSV ก่อนเติม. ร่างต้นทางยังอยู่ใน `LOCAL_REVIEW/DIALOGUE_CATALOG_DRAFT_20260831/` เพื่อใช้อ้างอิงเท่านั้น; การแก้ครั้งต่อไปให้แก้ `dialogue.csv` โดยตรง

ไฟล์ [reference_import.json](<D:/antigravity/board office/CHARACTER/DIALOGUE/reference_import.json>) บันทึกที่มาและเงื่อนไขครั้งแรกเท่านั้น ไม่ใช่ไฟล์ที่สร้าง CSV ใหม่ทุกครั้ง และไม่ใช่ยอดนับปัจจุบันหลังผู้ใช้แก้คลัง. เนื้อหานำเข้าตามคำขอของผู้ใช้; คำแปลไทยเป็นฉบับร่างของเรา ไม่ใช่ localization ไทยที่กู้คืนจากเกม

## วิธีแก้หรือเพิ่ม

1. บันทึก CSV เป็น UTF-8 (มีหรือไม่มี BOM ก็ได้). ถ้าข้อความมี comma หรือเครื่องหมายคำพูด ให้ quote ตามรูปแบบ CSV
2. แก้คอลัมน์ text เพื่อเปลี่ยนสิ่งที่ bubble แสดง. full_text เก็บฉบับเต็มแยกกันและไม่ถูกส่งเข้า renderer
3. เก็บ dialogue_id เดิมเมื่อแก้คำพูด เพื่อให้จุดที่อ้าง ID นั้นยังทำงาน. คำใหม่ใช้ ID ที่ไม่ซ้ำกับแถวภาษา/ลำดับเดียวกัน
4. เพิ่มภาษาโดยใช้ dialogue_id เดียวกันกับ locale ใหม่. ฟอนต์ปัจจุบันรองรับ en และ th; ภาษาอื่นต้องเพิ่ม font policy ก่อนเปิดใช้
5. category เพิ่มชื่อใหม่ได้โดยไม่ต้องแก้ enum ในโค้ด. การเพิ่มชื่อหมวดไม่ได้สร้างเงื่อนไข gameplay ให้เอง
6. enabled ใช้ true หรือ false เท่านั้น. ข้อความที่ปิดยังค้น/อ่านได้ แต่ API วาดจาก ID จะปฏิเสธ
7. หลังบันทึก เรียก central.reload_dialogue_content() เพื่อใช้กับ Central instance ที่กำลังทำงาน. หรือเริ่ม instance ใหม่เพื่ออ่าน CSV จากดิสก์ใหม่

การรีโหลดตรวจโครงสร้าง รายการซ้ำ แท็ก/ตัวแปรในข้อความที่เปิด และการพอดีใน bubble ของทุกแถวที่เปิด ก่อนสลับข้อมูลในหน่วยความจำ. ถ้าไม่ผ่าน จะคงคลังเดิมใน instance นั้นไว้และแจ้ง ID/แถวที่ผิด; ไม่ได้ย้อนคืนไฟล์บนดิสก์ให้เอง

| คอลัมน์ | ความหมาย |
| --- | --- |
| dialogue_id | ID ถาวรของคำพูด/ชุดบท; คีย์ไม่ซ้ำคือ dialogue_id + locale + line_index |
| locale | en หรือ th ตามฟอนต์ปัจจุบัน; en-US/th-TH ถูก normalize เป็นภาษาหลัก |
| line_index | เริ่มที่ 0; รองรับเก็บหลายบรรทัดในชุดบท แม้ตัวประสานตาพูดยังไม่ทำ |
| speaker_role | บทบาทผู้พูด เช่น speaker/listener; ไม่ได้สร้าง participant lock |
| text | ฉบับแสดงจริง บรรทัดเดียวและต้องพอดีกรอบเมื่อเปิดใช้ |
| category | หมวด เช่น greeting, fatigue, work_complete หรือหมวดใหม่ที่ตั้งเอง |
| usage_scope | office, context_only, future_activity, template, test หรือ scope ที่กำหนดเอง |
| enabled | true = อนุญาตการวาดจาก ID; false = เก็บไว้แต่ยังไม่วาด |
| full_text | ข้อความ/คำแปลฉบับเต็มเพื่อแก้ไขอ้างอิง ไม่ใช้วาดโดยอัตโนมัติ |
| source_id | ตำแหน่งแหล่งเดิม เช่น tv.text.L0872; คำที่เขียนใหม่ปล่อยว่างได้ |
| source_text | English ต้นฉบับเพื่ออ้างอิง ไม่ใช่ข้อความที่ต้องแสดง; คำใหม่ปล่อยว่างได้ |

ห้าคอลัมน์แรกยังเป็นสัญญาเดิม. ไฟล์เก่าที่ไม่มีคอลัมน์เสริมยังโหลดได้ โดยใช้ category=uncategorized, usage_scope=office, enabled=true และ full_text=text. รายการนำเข้ามี metadata ชัดเจนทุกแถว

ตัวอย่างแถวใหม่ (ใส่ใต้ header เดิม ไม่สร้าง header ซ้ำ):

~~~csv
greeting_new_001,en,0,speaker,Hi!,greeting,office,true,Hi!,,
greeting_new_001,th,0,speaker,หวัดดี!,greeting,office,true,สวัสดีจ้า,,
~~~

## เรียกจาก Central

~~~python
from RUNTIME.central_core import CentralGameCore

central = CentralGameCore(r"D:\antigravity\board office")
lines = central.list_dialogue_lines(
    locale="th",
    category="greeting",
    usage_scope="office",
    enabled_only=True,
)  # list of JSON-safe dictionaries

line = central.resolve_dialogue_line("phrase_text_0872", locale="th")
# line.text is the Thai display draft; line.full_text/source_text preserve reference text.

bubble = central.render_dialogue_line_for_character(
    "RND_F_004", "M0", "phrase_text_0872",
    locale="th", actor_top_left=(74, 68),
)

# Call after editing the CSV; a failed reload leaves the previous snapshot usable.
summary = central.reload_dialogue_content()
~~~

list_dialogue_lines() เมื่อไม่ใส่ filter จะคืนทุกแถว รวมตัวอย่างและแถวที่ปิด. สำหรับการเลือกในออฟฟิศต้องใส่ usage_scope="office", enabled_only=True และหมวดที่ตรงเหตุการณ์. API นี้ยังไม่สุ่ม ไม่หัก/เพิ่ม stamina และไม่ตรวจว่าเหตุการณ์นั้นเกิดแล้วจริง

## การเลือกบทสนทนาคู่และพูดคนเดียว

ตัวประสานบทสนทนาอยู่ที่ `RUNTIME/conversation_behavior_core.py` และเรียกผ่าน
`CentralGameCore.resolve_conversation_dialogue(...)` ได้โดยไม่เปลี่ยน assignment
หรือ state งาน. คู่สนทนาเลือกบรรทัดที่เปิดใช้จาก `conversation_open` ให้ผู้เริ่ม
และ `conversation_reply` ให้คู่สนทนา; ถ้าระบุ `category` จะเลือกสองบรรทัดต่าง ID
จากหมวดนั้น. Self-talk เลือกหนึ่งบรรทัดจาก pool ออฟฟิศทั่วไป โดยไม่นับสองหมวดคู่
ข้างต้น. การเรียก resolver โดยตรงยังใช้ hash ของผู้ร่วมสนทนา/seed/locale จึง replay ได้เหมือนเดิม
และเปลี่ยนข้อความใน CSV ได้โดยไม่ต้องแก้โค้ด. ส่วน speech scheduler ที่รันในงานจริงใช้
persistent shuffle bag แยกตาม locale/category: หยิบทุก line ที่เปิดใช้ให้ครบก่อน refill และเก็บ
recent-text cooldown สูงสุด 4 ข้อความเพื่อกันข้อความซ้ำติดกัน

~~~python
dialogue = central.resolve_conversation_dialogue(
    mode="standing_pair",
    participant_ids=["EMP_W1_0031", "EMP_W1_0010"],
    initiator_id="EMP_W1_0031",
    locale="th",
    selection_seed="event-001",
)
# dialogue["speaker_lines"] มีหนึ่งบรรทัดต่อคน เรียงผู้เริ่มก่อนคู่สนทนา
~~~

API render จาก ID ทั้ง CharacterSystem, Central character และ employee bridge ตรวจ enabled เหมือนกัน. resolve_dialogue_line() อ่านแถวที่ปิดได้เพื่อแก้ไข; ใส่ require_enabled=True เมื่อต้องการให้ปฏิเสธแถวที่ปิดตั้งแต่ lookup

## ขอบเขตและข้อควรระวัง

- รายการอ้างอิงเดิม 204 รายการและร่างที่ผู้ใช้อนุมัติอีก 800 รายการอยู่ในคลังครบ และแถว `office` เปิดใช้ครบหลังเพิ่ม adaptive font fallback (9→8→7→6→5→4 px) โดยไม่ wrap หรือ clip. แถว scope อื่นยังปิดและไม่เข้า automatic work speech
- ตัวแปรอย่าง <0> ยังไม่มีตัวแทนค่าใน slice นี้. ต้องแก้ text เป็นข้อความสุดท้ายและวัดใหม่ก่อนเปิดใช้; อย่าเปิด placeholder ให้ลอยบนหัว
- มีข้อความซ้ำข้าม ID ตามแหล่งเดิม. list คืนรายการตาม ID ไม่ได้รวมซ้ำหรือเพิ่มน้ำหนักให้เอง; scheduler ใช้ bag และ recent-text cooldown เพื่อไม่ให้ข้อความซ้ำติดกัน
- scheduler เลือกหมวด in-work ทั้ง 11 หมวด (`anticipation`, `work_progress`, `work_complete`, `encouragement`, `praise`, `celebration`, `disappointment`, `fatigue`, `surprise`, `uncertainty`, `idle_flavor`) ระหว่าง actor อยู่ `working` โดยไม่ผูก `encouragement/praise/celebration/disappointment/fatigue` กับผลลัพธ์คุยหรือการเดินทางกลับบ้าน. CSV เพียงเก็บเนื้อหา; scheduler เป็นผู้กำหนดจังหวะและ bag
- บทสนทนาคู่ การเดินเข้าหา การล็อกคู่ ลำดับผู้พูด bubble timing one-loop และ in-work category rotation ถูกผูกไว้ใน behavior slice แล้ว. ตัวละครจะออกจากโต๊ะเฉพาะ Talk หรือ Home; popup/VFX และบทพูดในงานยังคงนั่งที่ WorkSeat และไม่มี numeric score/stamina delta
- การแก้ข้อความยาวขึ้นจะวัดจากพิกเซลด้วยฟอนต์จริงและเลือก BB ที่เล็กที่สุดซึ่งพอดีตามลำดับ registry (`BB4`, `BB3`, `BB6`, `BB2`, `BB1`); ไม่สุ่มรูปทรง ไม่ตัด และไม่ wrap เงียบ ๆ. ถ้าไม่ได้ pin ขนาดฟอนต์ ระบบลดขนาด fallback ถึง 4 px เพื่อให้แถวที่เปิดใช้ render ได้
- อักขระนอกชุดฟอนต์ เช่น emoji/ภาษาใหม่ ต้องตรวจ glyph/fallback และภาพเพิ่ม. Pixel fit ไม่ได้ยืนยัน glyph coverage หรือการจัดวางภาษาไทยทั้งหมด. Pillow เครื่องนี้ยังไม่มี RAQM; gate ตรวจภาษา/ภาพยังเปิด

## Presentation ที่ใช้อยู่

ใช้ fukidashi_base เป็น whole crops อนุญาต BB1/BB2/BB3/BB4/BB6 และไม่ใช้ BB5. ขนาดฟอนต์มาตรฐาน 9 px (fallback อัตโนมัติถึง 4 px เมื่อจำเป็น). ระบบเลือก crop ที่เล็กที่สุดซึ่ง ink/advance พอดี safe rectangle; ไทยใช้ Noto Sans Thai กับ M+ 1p medium สำหรับ ASCII บน baseline เดียวกัน

หาง bubble อิงกลาง face alpha และ actor_frame_top_y + frame_bob_y - 20 จึงตามการเดินและ idle bob. ภาพ bubble และฟอนต์ยังเป็น development inputs ที่มี provenance ต้องเปลี่ยนตาม project-owned asset/font policy ก่อน canonical release. การนำเข้าคลังครั้งนี้ไม่ใช่การปิด phase หรือการยอมรับภาพ/ภาษาเพื่อ release
