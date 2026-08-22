"""Lightweight bilingual (English / Khmer) message helper.

Every message is defined with an English and a Khmer version.
``t()`` returns both, joined so the bot shows EN then KH side by side.
"""

from __future__ import annotations

# Each entry: key -> (english, khmer)
TRANSLATIONS: dict[str, tuple[str, str]] = {
    "welcome": (
        "Welcome! Please choose a service.",
        "សូមស្វាគមន៍! សូមជ្រើសរើសសេវាកម្ម",
    ),
    "ask_name": (
        "Please enter your name to view your CPD history!",
        "សូមបញ្ចូលឈ្មោះរបស់អ្នកដើម្បីមើលប្រវត្តិ CPD!",
    ),
    "cancel": ("Search cancelled.", "បានលុបចោលការស្វែងរក!"),
    "cancel_hint": (
        "You can send /cancel at any time to stop.",
        "អ្នកអាច /cancel បានគ្រប់ពេល ដើម្បីបញ្ឈប់",
    ),
    "ask_verification": (
        "Please enter your Name or Phone Number to view your CPD",
        "សូមបញ្ចូល ឈ្មោះ ឬ លេខទូរស័ព្ទ ដើម្បីមើលប្រវត្តិ CPD",
    ),
    "pickup_ask_name": (
        "Please enter the name of the pharmacist whose certificate(s) you are here to pick up.",
        "សូមបញ្ចូលឈ្មោះរបស់ឱសថការី ដែលអ្នកមកទទួលវិញ្ញាបនបត្រ។",
    ),
    "pickup_name_not_found": (
        "We could not find <b>{name}</b> in the system. Please check the "
        "spelling and try again, or type the phone number instead.",
        "រកមិនឃើញ <b>{name}</b> នៅក្នុងប្រព័ន្ធ។ សូមពិនិត្យអក្ខរាវិរុទ្ធ រួចព្យាយាមម្ដងទៀត ឬបញ្ចូលលេខទូរស័ព្ទជំនួសវិញ។",
    ),
    "pickup_who": (
        "Who is collecting the certificate(s)?",
        "តើអ្នកណាជាអ្នកមកទទួលវិញ្ញាបនបត្រ?",
    ),
    "pickup_self": ("The owner (myself)", "ម្ចាស់ខ្លួន"),
    "pickup_other": ("Someone else", "អ្នកផ្សេង"),
    "pickup_ask_picker": (
        "Please enter the name of the person who came to pick up the certificate(s).",
        "សូមបញ្ចូលឈ្មោះរបស់អ្នកដែលមកទទួលវិញ្ញាបនបត្រ។",
    ),
    "pickup_ask_course": (
        "Which course certificate(s) are you collecting? Tap course to "
        "select it, then confirm.",
        "តើអ្នកមកទទួលវិញ្ញាបនបត្រនៃវគ្គណាខ្លះ? សូមជ្រើសរើសវគ្គបណ្តុះបណ្តាល រួចចុចបញ្ជាក់។",
    ),
    "pickup_confirm": (
        "Confirm",
        "បញ្ជាក់",
    ),
    "pickup_confirm_none": (
        "Please select at least one course before confirming",
        "សូមជ្រើសរើសវគ្គបណ្តុះបណ្តាលយ៉ាងហោចណាស់មួយ មុនពេលចុចបញ្ជាក់",
    ),
    "pickup_no_courses": (
        "There are no completed courses to pick up certificates for.",
        "មិនមានវិញ្ញាបនបត្រដែលត្រូវមកទទួលទេ។",
    ),
    "pickup_not_ready": (
        "The certificate(s) for <b>{name}</b> are not ready yet:\n{courses}"
        "Please check back later.",
        "វិញ្ញាបនបត្ររបស់ <b>{name}</b> មិនទាន់រួចរាល់នៅឡើយ៖\n{courses}"
        "សូមពិនិត្យម្តងទៀតនៅពេលក្រោយ។",
    ),
    "pickup_saved": (
        "Certificate pickup recorded for <b>{name}</b> — {courses} at {time}.",
        "បានកត់ត្រាការទទួលវិញ្ញាបនបត្រ {courses} របស់ <b>{name}</b> នៅម៉ោង {time}។",
    ),
    "pickup_saved_by": (
        "Certificate pickup recorded for <b>{name}</b> — {courses} at {time}, received by <b>{by}</b>.",
        "បានកត់ត្រាការទទួលវិញ្ញាបនបត្រ {courses} របស់ <b>{name}</b> នៅម៉ោង {time} ដោយ <b>{by}</b>។",
    ),
    "pickup_admin_alert": (
        "📋 <b>Certificate pickup requested</b>\n\n"
        "Trainee: <b>{name}</b>\n"
        "Courses:\n{courses}"
        "Time: {time}\n"
        "Collected by: {by}\n"
        "Entered by: {sender}\n\n"
        "Please find and prepare the certificate(s) for the customer.",
        "📋 <b>មានសំណើសុំដកវិញ្ញាបនបត្រ</b>\n\n"
        "ឈ្មោះ: <b>{name}</b>\n"
        "វគ្គ:\n{courses}"
        "ម៉ោង: {time}\n"
        "ទទួលដោយ: {by}\n"
        "មកទទួលដោយ: {sender}\n\n"
        "សូមស្វែងរក និងរៀបចំវិញ្ញាបនបត្រសម្រាប់អតិថិជន។",
    ),
    "pickup_cancel": (
        "Pickup recording cancelled.",
        "បានលុបចោលការកត់ត្រាការទទួលវិញ្ញាបនបត្រ។",
    ),
    "ask_admin_view": (
        "Please enter the Name or Phone Number of the person you want to view.",
        "សូមបញ្ចូល ឈ្មោះ ឬ លេខទូរស័ព្ទ របស់អ្នកដែលអ្នកចង់មើល។",
    ),
    "account_linked": (
        "Your account is linked successfully! Welcome {name}.",
        "គណនីរបស់អ្នកត្រូវបានភ្ជាប់ដោយជោគជ័យ! សូមស្វាគមន៍ {name}។",
    ),
    "not_found_verification": (
        "No participant found with that Phone Number.\nPlease try again.",
        "រកមិនឃើញអ្នកចូលរួមដែលមានលេខទូរស័ព្ទនេះទេ។\nសូមព្យាយាមម្ដងទៀត។",
    ),
    "not_found": (
        "No participant found with the name \"{name}\".\n"
        "Please check the spelling, or try phone number!",
        "រកមិនឃើញអ្នកចូលរួមដែលមានឈ្មោះ \"{name}\" ទេ\n"
        "សូមពិនិត្យអក្ខរាវិរុទ្ធ ឬសាកល្បងលេខទូរស័ព្ទ!",
    ),
    "multiple_matches": (
        "I found {count} participants with a similar name. Please choose one:",
        "ខ្ញុំបានរកឃើញអ្នកចូលរួម {count} នាក់ដែលមានឈ្មោះប្រហាក់ប្រហែល។ សូមជ្រើសរើសមួយ៖",
    ),
    "section_training": ("Training History", "ប្រវត្តិបណ្ដុះបណ្ដាល"),
    "section_certificate": ("CPD Certificate Pickup", "ការទទួលវិញ្ញាបនបត្រ CPD"),
    "section_summary": ("Summary", "សង្ខេប"),
    "no_training": (
        "No training records found for this participant.",
        "រកមិនឃើញប្រវត្តិបណ្ដុះបណ្ដាលសម្រាប់អ្នកចូលរួមរូបនេះទេ។",
    ),
    "no_certificate": (
        "No certificate pickup records found for this participant.",
        "រកមិនឃើញប្រវត្តិវិញ្ញាបនបត្រសម្រាប់អ្នកចូលរួមរូបនេះទេ។",
    ),
    "picked_up": ("Picked up", "បានទទួល"),
    "not_picked_up": ("Not picked up", "មិនទាន់ទទួល"),
    "cert_ready": ("✅ Certificate ready", "✅ វិញ្ញាបនបត្ររួចរាល់"),
    "cert_not_ready": ("⏳ Certificate not ready yet", "⏳ វិញ្ញាបនបត្រមិនទាន់រួចរាល់"),
    "not_applicable": ("-", "-"),
    "your_telegram_id": (
        "Your Telegram ID is: <code>{tid}</code>\nShare this with the admin if you have an account linking problem.",
        "Telegram ID របស់អ្នកគឺ: <code>{tid}</code>\nចែករំលែកនេះជាមួយអ្នកគ្រប់គ្រង ប្រសិនបើអ្នកមានបញ្ហាភ្ជាប់គណនី។",
    ),
    "account_unlinked": (
        "Your account has been unlinked. Use /start to verify again.",
        "គណនីរបស់អ្នកត្រូវបានផ្ដាច់។ ប្រើ /start ដើម្បីផ្ទៀងផ្ទាត់ម្ដងទៀត។",
    ),
    "not_linked": (
        "Your account is not linked yet. Use /start to get started.",
        "គណនីរបស់អ្នកមិនទាន់ភ្ជាប់ទេ។ ប្រើ /start ដើម្បីចាប់ផ្ដើម។",
    ),
    "admin_only": (
        "⛔ This command is for admins only.",
        "⛔ ពាក្យបញ្ជានេះសម្រាប់តែអ្នកគ្រប់គ្រងប៉ុណ្ណោះ។",
    ),
    "search_again": ("Search another name", "ស្វែងរកឈ្មោះផ្សេងទៀត"),
    "done": (
        "Thank you! You can start a new search any time with /start.",
        "សូមអរគុណ! អ្នកអាចចាប់ផ្ដើមការស្វែងរកថ្មីនៅពេលណាក៏បានដោយផ្ញើ /start។",
    ),
    "menu_title": (
        "What would you like to see?",
        "តើអ្នកចង់មើលអ្វី?",
    ),
    "error": (
        "Sorry, something went wrong. Please try again later.",
        "សូមទោស មានបញ្ហាអ្វីមួយកើតឡើង។ សូមព្យាយាមម្ដងទៀតនៅពេលក្រោយ។",
    ),
    "loading_error": (
        "The CPD data files could not be loaded. Please contact the administrator.",
        "មិនអាចបើកឯកសារទិន្នន័យ CPD បានទេ។ សូមទាក់ទងអ្នកគ្រប់គ្រង។",
    ),
    "view_history": ("View History", "មើលប្រវត្តិ"),
    "further_info": (
        "For further information, please contact CPD officer Eng Sophanith (+855 98 448 619).",
        "ព័ត៌មានបន្ថែម សូមទាក់ទងលោក អៀង សុផានិត (Telegram: +855 98 448 619)។",
    ),
    "license_id": ("License ID", "លេខអាជ្ញាបណ្ណ"),
    "reg_pick_course": (
        "Please choose the course you want to register for:",
        "សូមជ្រើសរើសវគ្គបណ្តុះបណ្តាលដែលអ្នកចង់ចុះឈ្មោះ៖",
    ),
    "reg_already": (
        "You have already registered for this course!",
        "អ្នកបានចុះឈ្មោះសម្រាប់វគ្គនេះរួចហើយ!",
    ),
    "reg_ask_identity": (
        "Please enter your name!",
        "សូមបញ្ចូលឈ្មោះរបស់អ្នក!",
    ),
    "reg_ask_license": (
        "Please enter your pharmacist license number!",
        "សូមបញ្ចូលលេខបញ្ជិកាឱសថការីរបស់អ្នក!",
    ),
    "reg_ask_phone": (
        "Please enter your phone number!",
        "សូមបញ្ចូលលេខទូរស័ព្ទរបស់អ្នក!",
    ),
    "reg_ask_location": (
        "Please enter your​ location pharmacist council membership!",
        "សូមបញ្ចូលទីតាំងសមាជិកគណៈឱសថការីរបស់អ្នក!",
    ),
    "reg_ask_name": (
        "Please enter your name!",
        "សូមបញ្ចូលឈ្មោះរបស់អ្នក!",
    ),
    "reg_ask_khmer": (
        "Please also type your name in Khmer!",
        "សូមបញ្ចូលឈ្មោះជាភាសាខ្មែររបស់អ្នក!",
    ),
    "reg_ask_khmer_name": (
        "Please enter your name in Khmer!",
        "សូមបញ្ចូលឈ្មោះជាភាសាខ្មែររបស់អ្នក!",
    ),
    "reg_ask_latin": (
        "Please also type your name in Latin letters (English)!",
        "សូមបញ្ចូលឈ្មោះរបស់អ្នកជាអក្សរឡាតាំង (អង់គ្លេស) ផងដែរ!",
    ),
    "reg_confirm_old": (
        "Registered for course {course}.\nName: {name}\nLicense: {license}\n"
        "Date: {date}",
        "បានចុះឈ្មោះវគ្គ {course} ដោយជោគជ័យ។\nឈ្មោះ៖ {name}\nលេខបញ្ជិកា៖ {license}\n"
        "កាលបរិច្ឆេទ៖ {date}",
    ),
    "reg_confirm_new": (
        "Registered for course {course}.\nName: {name}\nLicense: {license}\n"
        "Phone: {phone}\nPharmacist council member: {location}\n"
        "Date: {date}",
        "បានចុះឈ្មោះវគ្គ {course} ដោយជោគជ័យ។\nឈ្មោះ៖ {name}\nលេខបញ្ជិកា៖ {license}\n"
        "ទូរស័ព្ទ៖ {phone}\nសមាជិកគណៈឱសថការី៖ {location}\n"
        "កាលបរិច្ឆេទ៖ {date}",
    ),
    "reg_join_group": (
        "Join the course group to receive updates:\n{link}",
        "សូមចូលរួមក្រុមវគ្គបណ្តុះបណ្តាលដើម្បីទទួលព័ត៌មាន៖\n{link}",
    ),
    "reg_join_group_button": (
        "Join course group",
        "ចូលរួមក្រុមវគ្គបណ្តុះបណ្តាល",
    ),
    "reg_no_group": (
        "The course group is not set up yet. Please contact the admin to join.",
        "ក្រុមវគ្គបណ្តុះបណ្តាលមិនទាន់បានរៀបចំទេ។ សូមទាក់ទងអ្នកគ្រប់គ្រងដើម្បីចូលរួម។",
    ),
    "reg_group_needs_admin": (
        "The course group is linked, but the bot must be made an administrator "
        "of it before invite links can be created. Please ask the admin to "
        "promote the bot in the group.",
        "ក្រុមវគ្គបានភ្ជាប់ហើយ ប៉ុន្តែត្រូវធ្វើឱ្យ bot ជាអ្នកគ្រប់គ្រងក្រុមនោះសិន "
        "មុនពេលអាចបង្កើតតំណភ្ជាប់បាន។ សូមទាក់ទងអ្នកគ្រប់គ្រងដើម្បីដំឡើង bot ក្នុងក្រុម។",
    ),
    "admin_group_usage": (
        "Usage: /admin_group &lt;Course ID&gt; (run inside the course group)",
        "ការប្រើប្រាស់៖ /admin_group &lt;លេខសម្គាល់វគ្គ&gt; (ប្រតិបត្តិក្នុងក្រុមវគ្គ)",
    ),
    "admin_setup_intro": (
        "Setup course groups: tap a button, choose the course's group "
        "(or create it in Telegram first) and the bot will link + rename it automatically.",
        "ការរៀបចំក្រុមវគ្គ៖ ចុចប៊ូតុង ជ្រើសរើសក្រុមវគ្គ "
        "(ឬបង្កើតវាក្នុង Telegram ជាមុន) បន្ទាប់មក bot នឹងភ្ជាប់ + ប្តូរឈ្មោះដោយស្វ័យប្រវត្តិ។",
    ),
    "admin_setup_button": (
        "Set up the group for this course",
        "រៀបចំក្រុមសម្រាប់វគ្គនេះ",
    ),
    "admin_setup_new_group": (
        "Create a new group",
        "បង្កើតក្រុមថ្មី",
    ),
    "admin_setup_needed": (
        "A participant registered for <b>{course}</b> ({course_id}) but no "
        "course group is set up yet. Tap below to link a group (the bot gets "
        "admin rights automatically):",
        "អ្នកចូលរួមបានចុះឈ្មោះសម្រាប់ <b>{course}</b> ({course_id}) ប៉ុន្តែមិនទាន់មានក្រុមវគ្គទេ។ "
        "ចុចខាងក្រោមដើម្បីភ្ជាប់ក្រុម (bot នឹងទទួលសិទ្ធិអ្នកគ្រប់គ្រងដោយស្វ័យប្រវត្តិ)៖",
    ),
    "admin_setup_no_courses": (
        "No open courses to set up.",
        "មិនមានវគ្គបើកសម្រាប់ការរៀបចំទេ។",
    ),
    "admin_group_not_group": (
        "This command must be run inside a Telegram group.",
        "ពាក្យបញ្ជានេះត្រូវតែប្រតិបត្តិក្នុងក្រុម Telegram មួយ។",
    ),
    "admin_group_unknown_course": (
        "No course found with ID {course_id}.",
        "រកមិនឃើញវគ្គដែលមានលេខសម្គាល់ {course_id} ទេ។",
    ),
    "admin_group_ok": (
        "Group linked to course {course} ({course_id}).",
        "បានភ្ជាប់ក្រុមជាមួយវគ្គ {course} ({course_id})។",
    ),
    "admin_group_make_admin": (
        "Please make this bot an administrator of the group first.",
        "សូមធ្វើឱ្យ bot នេះជាអ្នកគ្រប់គ្រងក្រុមជាមុនសិន។",
    ),
    "admin_help": (
        "<b>🛠 Admin commands</b>\n"
        "• /admin_setup — link/create a group for each open course\n"
        "• /admin_groups — list course ↔ group chat IDs\n"
        "• /admin_group_rename &lt;Course ID&gt; &lt;new title&gt; — rename a course group\n"
        "• /admin_group_clear &lt;Course ID&gt; — unlink a course group\n"
        "• /admin_regs — list registrations\n"
        "• /admin_reg_del &lt;telegram_id&gt; &lt;course_id&gt; — delete one registration\n"
        "• /admin_reg_add &lt;Course ID&gt; &lt;Name&gt; — register someone without Telegram (cash)\n"
        "• /admin_reg_move &lt;ID/Name&gt; &lt;From&gt; &lt;To&gt; — move a participant to another course\n"
        "• /admin_reg_clear — delete ALL registrations\n"
        "• /admin_confirm &lt;bill&gt; — mark a manual payment as Paid\n"
        "• /admin_courses — registrations & pickups per course\n"
        "• /admin_course &lt;Course ID&gt; — participants of one course with pickup status\n"
        "• /admin_kick &lt;Course ID&gt; &lt;telegram_id&gt; — remove a member from a course group\n"
        "• /admin_list — linked Telegram ↔ participant accounts\n"
        "• /admin_link &lt;ID&gt; &lt;Name&gt; / /admin_unlink &lt;ID or Name&gt;\n"
        "• /admin_view &lt;Name&gt; — view a participant's CPD history",
        "<b>🛠 ពាក្យបញ្ជាអ្នកគ្រប់គ្រង</b>\n"
        "• /admin_setup — ភ្ជាប់/បង្កើតក្រុមសម្រាប់វគ្គនីមួយៗ\n"
        "• /admin_groups — បញ្ជីវគ្គ ↔ លេខសម្គាល់ក្រុម\n"
        "• /admin_group_rename &lt;Course ID&gt; &lt;ឈ្មោះថ្មី&gt; — ប្តូរឈ្មោះក្រុមវគ្គ\n"
        "• /admin_group_clear &lt;Course ID&gt; — ផ្តាច់ក្រុមវគ្គ\n"
        "• /admin_regs — បញ្ជីការចុះឈ្មោះ\n"
        "• /admin_reg_del &lt;telegram_id&gt; &lt;course_id&gt; — លុបការចុះឈ្មោះមួយ\n"
        "• /admin_reg_add &lt;លេខវគ្គ&gt; &lt;ឈ្មោះ&gt; — ចុះឈ្មោះជំនួសអ្នកគ្មាន Telegram (សាច់ប្រាក់)\n"
        "• /admin_reg_move &lt;ID/ឈ្មោះ&gt; &lt;វគ្គចាស់&gt; &lt;វគ្គថ្មី&gt; — ផ្លាស់ទីអ្នកចូលរួមទៅវគ្គផ្សេង\n"
        "• /admin_reg_clear — លុបការចុះឈ្មោះទាំងអស់\n"
        "• /admin_confirm &lt;bill&gt; — បញ្ជាក់ការបង់ប្រាក់ដោយដៃ\n"
        "• /admin_courses — ការចុះឈ្មោះ និងការទទួលវិញ្ញាបនបត្រតាមវគ្គ\n"
        "• /admin_course &lt;លេខវគ្គ&gt; — បញ្ជីអ្នកចូលរួមមួយវគ្គ ជាមួយស្ថានភាពទទួលវិញ្ញាបនបត្រ\n"
        "• /admin_kick &lt;Course ID&gt; &lt;telegram_id&gt; — ដកសមាជិកចេញពីក្រុមវគ្គ\n"
        "• /admin_list — បញ្ជីគណនី Telegram ↔ អ្នកចូលរួម\n"
        "• /admin_link &lt;ID&gt; &lt;ឈ្មោះ&gt; / /admin_unlink &lt;ID ឬ ឈ្មោះ&gt;\n"
        "• /admin_view &lt;ឈ្មោះ&gt; — មើលប្រវត្តិ CPD របស់អ្នកចូលរួម",
    ),
    "admin_groups_title": (
        "Course groups ({count} linked):",
        "ក្រុមវគ្គ ({count} បានភ្ជាប់)៖",
    ),
    "admin_courses_title": (
        "<b>🎓 Courses — registrations & certificate pickups</b>",
        "<b>🎓 វគ្គសិក្សា — ការចុះឈ្មោះ និងការទទួលវិញ្ញាបនបត្រ</b>",
    ),
    "admin_courses_line": (
        "{icon} <b>{course}</b> — 👥 {total} registered · ✅ {picked} picked up",
        "{icon} <b>{course}</b> — 👥 {total} ចុះឈ្មោះ · ✅ {picked} បានទទួល",
    ),
    "admin_course_usage": (
        "Usage: /admin_course &lt;Course ID&gt;\n"
        "Example: /admin_course C002\n"
        "Tip: /admin_courses shows every course with totals.",
        "ការប្រើប្រាស់៖ /admin_course &lt;លេខវគ្គ&gt;\n"
        "ឧទាហរណ៍៖ /admin_course C002\n"
        "គន្លឹះ៖ /admin_courses បង្ហាញវគ្គទាំងអស់។",
    ),
    "admin_course_notfound": (
        "Course {course} not found. Valid IDs: {ids}",
        "រកមិនឃើញវគ្គ {course}។ លេខវគ្គត្រឹមត្រូវ៖ {ids}",
    ),
    "admin_course_title": (
        "<b>🎓 {course} — {title}</b>\n"
        "👥 {total} registered · ✅ {picked} picked up ({pct}%)",
        "<b>🎓 {course} — {title}</b>\n"
        "👥 {total} ចុះឈ្មោះ · ✅ {picked} បានទទួល ({pct}%)",
    ),
    "admin_course_empty": (
        "No verified registrations for this course yet.",
        "មិនទាន់មានការចុះឈ្មោះបានបញ្ជាក់សម្រាប់វគ្គនេះទេ។",
    ),
    "admin_course_picked_line": (
        "✅ {name} — picked up {date}",
        "✅ {name} — បានទទួល {date}",
    ),
    "admin_course_pending_line": (
        "⬜ {name} — not picked up yet",
        "⬜ {name} — មិនទាន់បានទទួល",
    ),
    "admin_reg_add_usage": (
        "Usage: /admin_reg_add &lt;Course ID&gt; &lt;Full Name&gt;\n"
        "Example: /admin_reg_add C002 Oeng Sopheap\n"
        "Registers someone without a Telegram account (walk-in / cash).",
        "ការប្រើប្រាស់៖ /admin_reg_add &lt;លេខវគ្គ&gt; &lt;ឈ្មោះពេញ&gt;\n"
        "ឧទាហរណ៍៖ /admin_reg_add C002 អេង សុភាព\n"
        "ចុះឈ្មោះជំនួសអ្នកដែលមិនមាន Telegram (បង់សាច់ប្រាក់)។",
    ),
    "admin_reg_add_notfound": (
        "Course {course} not found. Valid IDs: {ids}",
        "រកមិនឃើញវគ្គ {course}។ លេខវគ្គត្រូវ៖ {ids}",
    ),
    "admin_reg_add_ok": (
        "✅ Registered <b>{name}</b> for {course}\n"
        "<b>{title}</b>\n"
        "Status: Paid (recorded by admin)",
        "✅ បានចុះឈ្មោះ <b>{name}</b> ចូលវគ្គ {course}\n"
        "<b>{title}</b>\n"
        "ស្ថានភាព៖ បង់ប្រាក់រួច (ចុះដោយអ្នកគ្រប់គ្រង)",
    ),
    "admin_reg_add_dup": (
        "⚠️ {name} is already registered for {course}.",
        "⚠️ {name} បានចុះឈ្មោះវគ្គ {course} រួចហើយ។",
    ),
    "admin_reg_move_usage": (
        "Usage: /admin_reg_move &lt;Telegram ID or Full Name&gt; "
        "&lt;From Course&gt; &lt;To Course&gt;\n"
        "Example: /admin_reg_move 699463365 C001 C002\n"
        "Example: /admin_reg_move Oeng Sopheap C001 C002",
        "ការប្រើប្រាស់៖ /admin_reg_move &lt;Telegram ID ឬ ឈ្មោះពេញ&gt; "
        "&lt;វគ្គចាស់&gt; &lt;វគ្គថ្មី&gt;\n"
        "ឧទាហរណ៍៖ /admin_reg_move 699463365 C001 C002\n"
        "ឧទាហរណ៍៖ /admin_reg_move អេង សុភាព C001 C002",
    ),
    "admin_reg_move_notfound": (
        "No registration found for {who} in course {course}.",
        "រកមិនឃើញការចុះឈ្មោះរបស់ {who} ក្នុងវគ្គ {course} ទេ។",
    ),
    "admin_reg_move_dup": (
        "⚠️ {name} is already registered in {course}. Nothing moved.",
        "⚠️ {name} បានចុះឈ្មោះវគ្គ {course} រួចហើយ។ មិនបានផ្លាស់ទេ។",
    ),
    "admin_reg_move_same": (
        "⚠️ From and To course are identical.",
        "⚠️ វគ្គចាស់ និងវគ្គថ្មីដូចគ្នា។",
    ),
    "admin_reg_move_ok": (
        "✅ Moved <b>{name}</b>: {from_course} → {to_course}\n"
        "<b>{title}</b>{fee_line}",
        "✅ បានផ្លាស់ <b>{name}</b>: {from_course} → {to_course}\n"
        "<b>{title}</b>{fee_line}",
    ),
    "admin_reg_move_fee_up": (
        "\n💵 Please collect ${amount} difference.",
        "\n💵 សូមទទួលប្រាក់ខ្វះ ${amount}។",
    ),
    "admin_reg_move_fee_down": (
        "\n💵 Refund ${amount} to the participant.",
        "\n💵 សូមសងប្រាក់ ${amount} វិញ។",
    ),
    "admin_group_rename_usage": (
        "Usage: /admin_group_rename &lt;Course ID&gt; &lt;new title&gt;\n"
        "Example: /admin_group_rename C002 2026-09-15 Role of pharmacy in hospital",
        "ការប្រើប្រាស់៖ /admin_group_rename &lt;លេខវគ្គ&gt; &lt;ឈ្មោះថ្មី&gt;",
    ),
    "admin_group_rename_ok": (
        "Renamed group to <b>{title}</b>.",
        "បានប្តូរឈ្មោះក្រុមទៅជា <b>{title}</b>។",
    ),
    "admin_reg_del_usage": (
        "Usage: /admin_reg_del &lt;telegram_id&gt; &lt;course_id&gt;",
        "ការប្រើប្រាស់៖ /admin_reg_del &lt;telegram_id&gt; &lt;course_id&gt;",
    ),
    "admin_reg_del_ok": (
        "Deleted the registration for Telegram ID <code>{tid}</code> / course <b>{course}</b>.",
        "បានលុបការចុះឈ្មោះសម្រាប់ Telegram ID <code>{tid}</code> / វគ្គ <b>{course}</b>។",
    ),
    "admin_reg_del_notfound": (
        "No registration found for Telegram ID <code>{tid}</code> / course <b>{course}</b>.",
        "រកមិនឃើញការចុះឈ្មោះសម្រាប់ Telegram ID <code>{tid}</code> / វគ្គ <b>{course}</b> ទេ។",
    ),
    "admin_reg_clear_usage": (
        "Type <code>/admin_reg_clear yes</code> to confirm. This deletes ALL "
        "in-bot registrations.",
        "វាយ <code>/admin_reg_clear yes</code> ដើម្បីបញ្ជាក់។ វានឹងលុបការចុះឈ្មោះទាំងអស់។",
    ),
    "admin_reg_clear_ok": (
        "Deleted {count} registration(s).",
        "បានលុបការចុះឈ្មោះចំនួន {count} ។",
    ),
    "admin_kick_usage": (
        "Usage: /admin_kick &lt;Course ID&gt; &lt;telegram_id&gt;\n"
        "The bot must be an admin of the course group (with 'Ban users' right) "
        "to remove a member.",
        "ការប្រើប្រាស់៖ /admin_kick &lt;លេខវគ្គ&gt; &lt;telegram_id&gt;",
    ),
    "admin_kick_ok": (
        "Removed Telegram ID <code>{tid}</code> from the group of <b>{course}</b>.",
        "បានដក Telegram ID <code>{tid}</code> ចេញពីក្រុម <b>{course}</b>។",
    ),
    "admin_kick_nogroup": (
        "No group linked to course <b>{course}</b>.",
        "មិនមានក្រុមភ្ជាប់ជាមួយវគ្គ <b>{course}</b> ទេ។",
    ),
    "pay_intro": (
        "Please scan the QR code to pay <b>{amount} {currency}</b> for <b>{course}</b>.",
        "សូមស្កេន QR code ដើម្បីបង់ប្រាក់ <b>{amount} {currency}</b> សម្រាប់វគ្គ <b>{course}</b>។",
    ),
    "pay_intro_auto": (
        "Once paid, tap <b>\"I have paid\"</b> or wait a moment - I will "
        "confirm automatically.",
        "នៅពេលបានបង់រួច ចុច <b>\"ខ្ញុំបានបង់ប្រាក់ហើយ\"</b> ឬរង់ចាំមួយភ្លែត - "
        "ខ្ញុំនឹងបញ្ជាក់ដោយស្វ័យប្រវត្តិ។",
    ),
    "pay_check_button": (
        "I have paid",
        "ខ្ញុំបានបង់ប្រាក់ហើយ",
    ),
    "pay_cancel_button": (
        "Cancel registration",
        "បោះបង់ការចុះឈ្មោះ",
    ),
    "pay_unpaid": (
        "We could not confirm your payment yet. Please scan the QR code and "
        "pay first, then tap the button again.",
        "យើងមិនទាន់អាចបញ្ជាក់ការបង់ប្រាក់របស់អ្នកបានទេ។ សូមស្កេន QR code និងបង់ប្រាក់ជាមុនសិន "
        "បន្ទាប់មកចុចប៊ូតុងម្តងទៀត។",
    ),
    "pay_manual_mode": (
        "",
        "",
    ),
    "pay_success": (
        "Payment confirmed! <b>{amount} {currency}</b> received for "
        "<b>{course}</b>.",
        "ការបង់ប្រាក់ត្រូវបានបញ្ជាក់! បានទទួល <b>{amount} {currency}</b> សម្រាប់វគ្គ "
        "<b>{course}</b>។",
    ),
    "pay_success_pending": (
        "We received your payment confirmation for <b>{amount} {currency}</b>. "
        "An admin will verify it shortly and complete your registration.",
        "យើងបានទទួលការបញ្ជាក់ការបង់ប្រាក់របស់អ្នក <b>{amount} {currency}</b> ហើយ។ "
        "អ្នកគ្រប់គ្រងនឹងផ្ទៀងផ្ទាត់ក្នុងពេលឆាប់ៗនេះ និងបញ្ចប់ការចុះឈ្មោះរបស់អ្នក។",
    ),
    "pay_expired": (
        "The payment window for this registration has expired. Please start "
        "again with /start.",
        "ពេលវេលាបង់ប្រាក់សម្រាប់ការចុះឈ្មោះនេះបានផុតកំណត់ហើយ។ សូមចាប់ផ្តើមម្តងទៀតជាមួយ /start។",
    ),
    "pay_not_configured": (
        "Online payment is not set up yet. Please contact the admin to "
        "complete your registration.",
        "ការបង់ប្រាក់តាមអនឡាញមិនទាន់ត្រូវបានរៀបចំទេ។ សូមទាក់ទងអ្នកគ្រប់គ្រងដើម្បីបញ្ចប់ការចុះឈ្មោះរបស់អ្នក។",
    ),
    "reg_confirm_paid": (
        "Registered for course {course}.\nName: {name}\nLicense: {license}\n"
        "Phone: {phone}\nPharmacist council member: {location}\n"
        "Date: {date}\n{payment_line}",
        "បានចុះឈ្មោះវគ្គ {course} ដោយជោគជ័យ។\nឈ្មោះ៖ {name}\nលេខបញ្ជិកា៖ {license}\n"
        "ទូរស័ព្ទ៖ {phone}\nសមាជិកគណៈឱសថការី៖ {location}\n"
        "កាលបរិច្ឆេទ៖ {date}\n{payment_line}",
    ),
    "payment_line_ok": (
        "Payment: {amount} {currency} ✔",
        "ការទូទាត់៖ {amount} {currency} ✔",
    ),
    "payment_line_pending": (
        "Payment: {amount} {currency} ⏳ (awaiting admin confirmation)",
        "ការទូទាត់៖ {amount} {currency} ⏳ (រង់ចាំការបញ្ជាក់ពីអ្នកគ្រប់គ្រង)",
    ),
}

DEFAULT_LANG = "en"


def t(key: str) -> str:
    """Return the Khmer string for *key*."""
    pair = TRANSLATIONS.get(key)
    if pair is None:
        raise KeyError(f"Unknown translation key: {key}")
    _, kh = pair
    return kh


def inline(key: str, **kwargs) -> str:
    """Return the Khmer string for *key*."""
    pair = TRANSLATIONS.get(key)
    if pair is None:
        raise KeyError(f"Unknown translation key: {key}")
    _, kh = pair
    return kh.format(**kwargs)


def fmt(key: str, **kwargs) -> str:
    """Return the Khmer string formatted with the given keyword args."""
    pair = TRANSLATIONS.get(key)
    if pair is None:
        raise KeyError(f"Unknown translation key: {key}")
    _, kh = pair
    return kh.format(**kwargs)