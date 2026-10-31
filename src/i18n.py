"""Lightweight interface translation (English <-> Khmer).

Source strings in the code stay English. When Khmer is active, widget texts are looked up in KM and replaced;
the English original is remembered on the widget so switching back (or re-translating) always works.
Unknown strings (dynamic messages, file names, numbers) are left unchanged."""
from __future__ import annotations

import re

from PySide6.QtCore import QEvent, QObject
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QAbstractButton, QApplication, QComboBox, QLabel, QLineEdit, QMenu, QPlainTextEdit,
                               QWidget)

LANGUAGES = (("en", "English"), ("km", "ខ្មែរ"))

KM: dict[str, str] = {
    # menus & toolbar
    "File": "ឯកសារ", "Edit": "កែសម្រួល", "Presets": "គំរូរចនា", "View": "ទិដ្ឋភាព", "Help": "ជំនួយ",
    "Language": "ភាសា", "New": "ថ្មី", "Open": "បើក", "Open…": "បើក…", "Save": "រក្សាទុក", "Save As…": "រក្សាទុកជា…",
    "Undo": "មិនធ្វើវិញ", "Redo": "ធ្វើវិញ", "Reset": "កំណត់ឡើងវិញ", "Export": "នាំចេញ", "Export…": "នាំចេញ…",
    "Quit": "ចាកចេញ", "About": "អំពី", "Open Recent": "បើកថ្មីៗ", "Recent Projects…": "គម្រោងថ្មីៗ…",
    "Batch Generate from CSV…": "បង្កើតច្រើនពី CSV…", "Create Print Sheet…": "បង្កើតសន្លឹកបោះពុម្ព…",
    "Design Templates…": "គំរូការរចនា…", "Design Templates": "គំរូការរចនា", "Open Preset…": "បើកគំរូ…",
    "Save Preset…": "រក្សាទុកគំរូ…", "Save Preset": "រក្សាទុកគំរូ", "Saved Presets": "គំរូដែលបានរក្សាទុក",
    "Upload Center Logo…": "ផ្ទុកឡើងឡូហ្គោកណ្តាល…", "Upload Center Logo": "ផ្ទុកឡើងឡូហ្គោកណ្តាល",
    "Fit to Window": "សមនឹងបង្អួច", "Zoom In": "ពង្រីក", "Zoom Out": "បង្រួម", "Properties Panel": "ផ្ទាំងលក្ខណៈ",
    "Dark mode": "របៀបងងឹត", "Light mode": "របៀបភ្លឺ", "Check for Updates…": "ពិនិត្យមើលការអាប់ដេត…",
    "Check for updates automatically": "ពិនិត្យការអាប់ដេតដោយស្វ័យប្រវត្តិ",
    "No recent projects": "មិនទាន់មានគម្រោងថ្មីៗ", "No saved presets yet": "មិនទាន់មានគំរូដែលបានរក្សាទុក",
    # sections
    "Content": "មាតិកា", "Logo": "ឡូហ្គោ", "QR Colors": "ពណ៌ QR", "Finder Eyes": "ភ្នែកស្កេន",
    "Frame Designer": "ឧបករណ៍រចនាស៊ុម", "Live preview": "ការមើលជាមុនផ្ទាល់", "Preview": "មើលជាមុន", "Fit": "សម",
    # content types
    "Website URL": "គេហទំព័រ (URL)", "Plain text": "អក្សរធម្មតា", "E-mail": "អ៊ីមែល", "Phone number": "លេខទូរស័ព្ទ",
    "SMS message": "សារ SMS", "Wi-Fi network": "បណ្តាញ Wi-Fi", "Contact card (vCard)": "កាតទំនាក់ទំនង (vCard)",
    "Map location": "ទីតាំងលើផែនទី", "Calendar event": "ព្រឹត្តិការណ៍ប្រតិទិន", "WhatsApp chat": "ជជែក WhatsApp",
    "Telegram link": "តំណ Telegram",
    "URL": "URL", "To": "ទៅ", "Subject": "ប្រធានបទ", "Body": "ខ្លឹមសារ", "Number": "លេខ", "Message": "សារ",
    "Network": "បណ្តាញ", "Security": "សុវត្ថិភាព", "Password": "ពាក្យសម្ងាត់", "Hidden network": "បណ្តាញលាក់",
    "No password": "គ្មានពាក្យសម្ងាត់", "Name": "ឈ្មោះ", "Company": "ក្រុមហ៊ុន", "Phone": "ទូរស័ព្ទ", "Website": "គេហទំព័រ",
    "Latitude": "រយៈទទឹង", "Longitude": "រយៈបណ្តោយ", "Title": "ចំណងជើង", "Starts": "ចាប់ផ្តើម", "Ends": "បញ្ចប់",
    "Location": "ទីតាំង", "Notes": "កំណត់ចំណាំ", "Username": "ឈ្មោះអ្នកប្រើ",
    "Error correction": "ការកែកំហុស", "Quiet zone": "តំបន់ស្ងាត់", "Type": "ប្រភេទ",
    "L – Low (~7% recovery)": "L – ទាប (~៧%)", "M – Medium (~15%)": "M – មធ្យម (~១៥%)",
    "Q – Quartile (~25%)": "Q – ខ្ពស់ល្មម (~២៥%)", "H – High (~30%)": "H – ខ្ពស់ (~៣០%)",
    "Higher levels survive more damage but make denser codes.": "កម្រិតខ្ពស់ទប់ទល់ការខូចខាតបានល្អជាង ប៉ុន្តែកូដកាន់តែក្រាស់។",
    "Any text – Unicode and Khmer are supported": "អក្សរណាក៏បាន – គាំទ្រ Unicode និងភាសាខ្មែរ",
    # logo
    "Remove logo": "ដកឡូហ្គោចេញ", "Locate missing logo…": "ស្វែងរកឡូហ្គោដែលបាត់…", "Show logo in the centre": "បង្ហាញឡូហ្គោនៅកណ្តាល",
    "Size": "ទំហំ", "Backing": "ផ្ទៃក្រោយឡូហ្គោ", "Backing colour": "ពណ៌ផ្ទៃក្រោយ", "Padding": "គម្លាតខាងក្នុង",
    "Use error correction level H with a logo": "ប្រើការកែកំហុសកម្រិត H ពេលមានឡូហ្គោ",
    "No logo selected. PNG (transparent OK), JPG or SVG.": "មិនទាន់ជ្រើសឡូហ្គោ។ PNG (ថ្លាបាន), JPG ឬ SVG។",
    "The logo is a visual overlay only – it is never part of the encoded data.":
        "ឡូហ្គោគ្រាន់តែជារូបភាពគ្របពីលើប៉ុណ្ណោះ – វាមិនមែនជាផ្នែកនៃទិន្នន័យដែលបានអ៊ិនកូដឡើយ។",
    "Transparent (no backing)": "ថ្លា (គ្មានផ្ទៃក្រោយ)", "Rounded square": "ការ៉េជ្រុងមូល", "Circle / badge": "រង្វង់ / ផ្លាក",
    "White padding / square": "គម្លាតពណ៌ស / ការ៉េ",
    # colours / eyes
    "Preset": "គំរូពណ៌", "Foreground": "ពណ៌ខាងមុខ", "Background": "ពណ៌ផ្ទៃខាងក្រោយ",
    "Transparent background (PNG / SVG / PDF)": "ផ្ទៃខាងក្រោយថ្លា (PNG / SVG / PDF)", "Module style": "រចនាបថម៉ូឌុល",
    "Gradient foreground": "ពណ៌ខាងមុខជាក្រឌីយ៉ង់", "Gradient end": "ពណ៌ចុងក្រឌីយ៉ង់", "Angle": "មុំ",
    "Square": "ការ៉េ", "Rounded": "ជ្រុងមូល", "Dots": "ចំណុច", "Small dots": "ចំណុចតូច", "Gapped squares": "ការ៉េមានគម្លាត",
    "Vertical bars": "ដងឈរ", "Circle": "រង្វង់",
    "Classic Black & White": "ខ្មៅ-ស បែបបុរាណ", "Corporate Blue": "ខៀវក្រុមហ៊ុន", "Crimson Red": "ក្រហមចាស់",
    "Emerald Green": "បៃតងត្បូងមរកត", "Dark Premium": "ងងឹតប្រណីត", "Purple Modern": "ស្វាយទំនើប",
    "Custom Brand Colors": "ពណ៌ម៉ាកផ្ទាល់ខ្លួន",
    "Gradients and light-on-dark colours can hurt scan reliability. Keep strong contrast.":
        "ក្រឌីយ៉ង់ និងពណ៌ភ្លឺលើងងឹត អាចធ្វើឱ្យស្កេនពិបាក។ សូមរក្សាកម្រិតកម្រិតភាពផ្ទុយខ្ពស់។",
    "Use the foreground colour for the eyes": "ប្រើពណ៌ខាងមុខសម្រាប់ភ្នែក", "Outer colour": "ពណ៌ក្រៅ", "Outer style": "រចនាបថក្រៅ",
    "Pupil colour": "ពណ៌ផ្ចិត", "Pupil style": "រចនាបថផ្ចិត",
    "The three large corner markers are used by scanners to find the code. Square or rounded eyes are the safest.":
        "សញ្ញាធំទាំងបីនៅជ្រុង ត្រូវបានម៉ាស៊ីនស្កេនប្រើដើម្បីរកកូដ។ ភ្នែកការ៉េ ឬជ្រុងមូល គឺមានសុវត្ថិភាពបំផុត។",
    # frame
    "No frame": "គ្មានស៊ុម", "Simple rectangle": "ចតុកោណសាមញ្ញ", "Rounded rectangle": "ចតុកោណជ្រុងមូល", "Rounded card": "កាតជ្រុងមូល",
    "Double line": "បន្ទាត់ពីរជាន់", "Corporate (header bar)": "ក្រុមហ៊ុន (របារក្បាល)", "Call-to-action (button)": "ប៊ូតុងអំពាវនាវ",
    "Frame colour": "ពណ៌ស៊ុម", "Canvas colour": "ពណ៌ផ្ទៃបោះពុម្ព", "Thickness": "កម្រាស់", "Corner radius": "កាំជ្រុង",
    "Inner padding": "គម្លាតខាងក្នុង", "Outer margin": "គម្លាតខាងក្រៅ", "Min. width": "ទទឹងអប្បបរមា", "Min. height": "កម្ពស់អប្បបរមា",
    "Border": "ស៊ុម", "Solid": "ខ្សែរឹង", "Dashed": "ខ្សែដាច់ៗ", "Caption": "ពាក្យពណ៌នា", "Font": "ពុម្ពអក្សរ",
    "Font size": "ទំហំអក្សរ", "Weight": "កម្រាស់អក្សរ", "Regular": "ធម្មតា", "Bold": "ដិត", "Text colour": "ពណ៌អក្សរ",
    "Bar text": "អក្សរលើរបារ", "Text gap": "គម្លាតអក្សរ", "Top": "លើ", "Bottom": "ក្រោម", "   position": "   ទីតាំង",
    "Text is placed outside the QR code and its quiet zone, so it never covers modules.":
        "អក្សរត្រូវបានដាក់នៅខាងក្រៅ QR និងតំបន់ស្ងាត់របស់វា ដូច្នេះមិនគ្របលើម៉ូឌុលឡើយ។",
    "Visit our website": "ចូលមើលគេហទំព័ររបស់យើង", "Your company": "ក្រុមហ៊ុនរបស់អ្នក", "SCAN ME": "ស្កេនខ្ញុំ",
    # export
    "Format": "ទ្រង់ទ្រាយ", "Width": "ទទឹង", "Resolution": "គុណភាពបោះពុម្ព", "JPEG quality": "គុណភាព JPEG",
    "QR size in layout": "ទំហំ QR ក្នុងប្លង់",
    "PNG – best quality, supports transparency": "PNG – គុណភាពល្អបំផុត គាំទ្រផ្ទៃថ្លា",
    "JPG – small files for sharing": "JPG – ឯកសារតូច សម្រាប់ចែករំលែក",
    "SVG – vector (scales without blur)": "SVG – វ៉ិចទ័រ (ពង្រីកមិនព្រិល)", "PDF – print ready": "PDF – រួចរាល់សម្រាប់បោះពុម្ព",
    # properties
    "QR code": "កូដ QR", "Modules": "ម៉ូឌុល", "Output": "លទ្ធផល", "Colours": "ពណ៌", "Style": "រចនាបថ", "Frame": "ស៊ុម",
    "Scan reliability": "ភាពអាចស្កេនបាន", "No centre logo.": "គ្មានឡូហ្គោកណ្តាល។", "No frame.": "គ្មានស៊ុម។",
    "Enter the content to encode and the QR code will appear here.": "បញ្ចូលមាតិកា នោះកូដ QR នឹងបង្ហាញនៅទីនេះ។",
    "No QR code is guaranteed to scan in every situation. Always test the final design with several phones, at the real print size, before distributing it.":
        "គ្មានកូដ QR ណាអាចធានាថាស្កេនបានគ្រប់ស្ថានភាពទេ។ សូមសាកល្បងការរចនាចុងក្រោយជាមួយទូរស័ព្ទច្រើនគ្រឿង ក្នុងទំហំបោះពុម្ពពិត មុនចែកចាយ។",
    "✓ Scans OK": "✓ ស្កេនបាន", "⚠ May not scan": "⚠ ប្រហែលស្កេនមិនបាន", "Checking scan…": "កំពុងពិនិត្យការស្កេន…",
    # tools
    "Browse…": "រុករក…", "Cancel": "បោះបង់", "Close": "បិទ", "Open folder": "បើកថតឯកសារ", "Generate": "បង្កើត",
    "Create PDF…": "បង្កើត PDF…", "Save example CSV…": "រក្សាទុកឯកសារ CSV គំរូ…", "Use template": "ប្រើគំរូនេះ",
    "Content": "មាតិកា", "Treat content as": "ចាត់ទុកមាតិកាជា",
    "Automatic (URL if it looks like one)": "ស្វ័យប្រវត្តិ (ជា URL បើមើលទៅដូច URL)", "Always a web URL": "តែងតែជា URL គេហទំព័រ",
    "Always plain text": "តែងតែជាអក្សរធម្មតា", "Choose a CSV file…": "ជ្រើសរើសឯកសារ CSV…",
    "Choose an output folder…": "ជ្រើសរើសថតទុកលទ្ធផល…",
    "Create one QR code per CSV row, using the current design (colours, logo, frame, size and format). Columns: content (URL or text), and optionally filename, title, caption, company.":
        "បង្កើតកូដ QR មួយសម្រាប់មួយជួរក្នុង CSV ដោយប្រើការរចនាបច្ចុប្បន្ន (ពណ៌ ឡូហ្គោ ស៊ុម ទំហំ និងទ្រង់ទ្រាយ)។ ជួរឈរ៖ content (URL ឬអក្សរ) និងអាចមាន filename, title, caption, company។",
    "Batch generate from CSV": "បង្កើតច្រើនពី CSV", "Create print sheet": "បង្កើតសន្លឹកបោះពុម្ព",
    "Arrange QR codes on a printable A4 / Letter PDF with cut guides - handy for stickers, table tents and labels.":
        "រៀបកូដ QR លើ PDF ទំហំ A4 / Letter សម្រាប់បោះពុម្ព ព្រមទាំងបន្ទាត់កាត់ – ងាយស្រួលសម្រាប់ស្ទីគ័រ និងស្លាក។",
    "Repeat the current design": "ចម្លងការរចនាបច្ចុប្បន្ន", "One code per CSV row (uses the current design)":
        "កូដមួយសម្រាប់មួយជួរ CSV (ប្រើការរចនាបច្ចុប្បន្ន)", "Draw cut guides": "គូរបន្ទាត់កាត់",
    "Paper": "ក្រដាស", "Sticker size": "ទំហំស្ទីគ័រ", "Margin": "គែម", "Gap": "គម្លាត",
    "A4 (210 × 297 mm)": "A4 (២១០ × ២៩៧ មម)", "US Letter (8.5 × 11 in)": "US Letter (៨.៥ × ១១ អ៊ីញ)",
    "Design templates": "គំរូការរចនា", "Recent projects": "គម្រោងថ្មីៗ",
    "Pick a starting look. Your content and logo are kept; you can fine-tune everything afterwards and undo with Ctrl+Z.":
        "ជ្រើសរើសទម្រង់ចាប់ផ្តើម។ មាតិកា និងឡូហ្គោរបស់អ្នកនៅដដែល អ្នកអាចកែសម្រួលបន្តទៀត និងមិនធ្វើវិញដោយ Ctrl+Z។",
    "No recent projects yet. Save a project and it will appear here.": "មិនទាន់មានគម្រោងថ្មីៗ។ រក្សាទុកគម្រោង នោះវានឹងបង្ហាញនៅទីនេះ។",
    "Ready – everything runs offline on your computer.": "ត្រៀមរួច – អ្វីៗដំណើរការក្រៅបណ្តាញលើកុំព្យូទ័ររបស់អ្នក។",
    # templates

    # hub & converters (added in 1.2.0)
    "TL Studio Pro": "TL Studio Pro", "Coming soon": "ឆាប់ៗនេះ", "This tool is coming in the next update.": "ឧបករណ៍នេះនឹងមកក្នុងការអាប់ដេតបន្ទាប់។",
    "Your all-in-one toolbox. Everything runs on your computer.": "ប្រអប់ឧបករណ៍ទាំងអស់ក្នុងមួយ។ អ្វីៗដំណើរការលើកុំព្យូទ័ររបស់អ្នក។",
    "QR STUDIO PRO": "QR STUDIO PRO", "Download Image & Video": "ទាញយករូបភាព និងវីដេអូ", "Convert Studio": "ស្ទូឌីយោបម្លែងឯកសារ",
    "Convert Media": "បម្លែងមេឌៀ", "PDF to Form": "PDF ទៅទម្រង់បែបបទ", "AI Agent": "ភ្នាក់ងារ AI",
    "Excel → PDF": "Excel → PDF", "PDF → Word": "PDF → Word", "PDF → Excel": "PDF → Excel", "Word → PDF": "Word → PDF",
    "Excel ↔ CSV": "Excel ↔ CSV", "Images → PDF": "រូបភាព → PDF", "PDF → Images": "PDF → រូបភាព", "Merge PDF": "បញ្ចូល PDF",
    "Split PDF": "បំបែក PDF", "Excel to PDF": "Excel ទៅ PDF", "PDF to Word": "PDF ទៅ Word", "PDF to Excel": "PDF ទៅ Excel",
    "Word to PDF": "Word ទៅ PDF", "Images to PDF": "រូបភាពទៅ PDF", "PDF to images": "PDF ទៅរូបភាព",
    "Split / extract pages": "បំបែក / ដកទំព័រចេញ",
    "Convert image": "បម្លែងរូបភាព", "Resize": "ប្តូរទំហំ", "Crop": "កាត់", "Rotate / flip": "បង្វិល / ត្រឡប់", "Compress image": "បង្រួមរូបភាព",
    "Images → GIF": "រូបភាព → GIF", "Edit GIF": "កែ GIF", "GIF → frames": "GIF → ស៊ុម", "Video → GIF": "វីដេអូ → GIF",
    "Convert video": "បម្លែងវីដេអូ", "Trim video": "កាត់វីដេអូ", "Extract audio": "ដកសំឡេង",
    "Make a PDF fillable": "ធ្វើឱ្យ PDF អាចបំពេញបាន", "Fill a form": "បំពេញទម្រង់បែបបទ",
    "Add files…": "បន្ថែមឯកសារ…", "Choose file…": "ជ្រើសរើសឯកសារ…", "Remove": "ដកចេញ", "Clear": "សម្អាត", "Move up": "ឡើងលើ",
    "Move down": "ចុះក្រោម", "Convert": "បម្លែង", "Merge": "បញ្ចូល", "Split": "បំបែក", "Compress": "បង្រួម", "Apply": "អនុវត្ត",
    "Extract": "ដកចេញ", "Trim": "កាត់", "Make GIF": "បង្កើត GIF", "Find fields": "ស្វែងរកវាល", "Create fillable PDF": "បង្កើត PDF ដែលអាចបំពេញបាន",
    "Open PDF": "បើក PDF", "Save filled PDF": "រក្សាទុក PDF ដែលបានបំពេញ", "Save CSV template…": "រក្សាទុកគំរូ CSV…",
    "Fill from CSV…": "បំពេញពី CSV…", "All": "ទាំងអស់", "None": "គ្មាន", "Add": "បន្ថែម", "Page": "ទំព័រ", "Field name": "ឈ្មោះវាល",
    "Label": "ស្លាក", "Check box": "ប្រអប់ធីក", "Text": "អក្សរ", "Page size": "ទំហំទំព័រ", "File name": "ឈ្មោះឯកសារ", "Pages": "ទំព័រ",
    "Convert to": "បម្លែងទៅជា", "Quality": "គុណភាព", "Height": "កម្ពស់", "Left": "ឆ្វេង", "Top": "លើ", "Percent": "ភាគរយ", "or percent": "ឬភាគរយ",
    "Keep proportions": "រក្សាសមាមាត្រ", "Flip horizontally": "ត្រឡប់ផ្ដេក", "Flip vertically": "ត្រឡប់បញ្ឈរ", "Rotate": "បង្វិល",
    "Speed": "ល្បឿន", "Colours": "ពណ៌", "Play backwards": "ចាក់ថយក្រោយ", "Loop forever": "ចាក់ដដែលៗ", "Delay per frame": "ពេលក្នុងមួយស៊ុម",
    "Start at": "ចាប់ផ្តើមនៅ", "Start": "ចាប់ផ្តើម", "End (0 = to the end)": "បញ្ចប់ (0 = ដល់ចុង)", "Save as": "រក្សាទុកជា",
    "Put all tables on one sheet": "ដាក់តារាងទាំងអស់លើសន្លឹកតែមួយ", "Save every page as its own PDF": "រក្សាទុកទំព័រនីមួយៗជា PDF ដាច់ដោយឡែក",
    "Flatten (make the values permanent text, no longer editable)": "បង្រួម (ធ្វើឱ្យតម្លៃជាអក្សរអចិន្ត្រៃយ៍ មិនអាចកែបានទៀត)",
    "Save next to the original file (or choose a folder…)": "រក្សាទុកក្បែរឯកសារដើម (ឬជ្រើសរើសថត…)",
    "More online tools: ezgif.com": "ឧបករណ៍អនឡាញបន្ថែម៖ ezgif.com",
    "Turn spreadsheets (.xlsx, .xls, .csv) into PDF documents. Every sheet becomes pages.":
        "បម្លែងសៀវភៅបញ្ជី (.xlsx, .xls, .csv) ទៅជាឯកសារ PDF។ សន្លឹកនីមួយៗក្លាយជាទំព័រ។",
    "Join several PDFs into one, in the order shown below.": "បញ្ចូល PDF ច្រើនជាមួយ តាមលំដាប់ដែលបង្ហាញខាងក្រោម។",
    "Save every page of a PDF as a picture.": "រក្សាទុកគ្រប់ទំព័រនៃ PDF ជារូបភាព។",
    "Change the format of pictures. Animated GIF and WebP keep their animation.": "ប្តូរទ្រង់ទ្រាយរូបភាព។ GIF និង WebP មានចលនារក្សាចលនារបស់វា។",
    "Cut a rectangle out of a picture.": "កាត់ចតុកោណពីរូបភាព។", "Cut a video to a shorter clip.": "កាត់វីដេអូឱ្យខ្លីជាងមុន។",
    "Save the sound of a video as an audio file.": "រក្សាទុកសំឡេងរបស់វីដេអូជាឯកសារសំឡេង។",
    "Make an animated GIF from part of a video.": "បង្កើត GIF មានចលនាពីផ្នែកមួយនៃវីដេអូ។",
    "Open an ordinary PDF. TL Studio Pro finds the blanks (lines, boxes, check boxes), you review them, and it adds real form fields you can type into in any PDF reader.":
        "បើក PDF ធម្មតា។ TL Studio Pro នឹងរកកន្លែងទទេ (បន្ទាត់ ប្រអប់ ប្រអប់ធីក) អ្នកពិនិត្យ ហើយវាបន្ថែមវាលទម្រង់ពិតប្រាកដដែលអ្នកអាចវាយបញ្ចូលក្នុងកម្មវិធីអាន PDF ណាក៏បាន។",
    "Open a fillable PDF, type the values and save a filled copy. For many people at once, use a CSV file (one row per form).":
        "បើក PDF ដែលអាចបំពេញបាន វាយតម្លៃ ហើយរក្សាទុកច្បាប់ចម្លងដែលបានបំពេញ។ សម្រាប់មនុស្សច្រើននាក់ក្នុងពេលតែមួយ ប្រើឯកសារ CSV (មួយជួរក្នុងមួយទម្រង់)។",
    "Choose a PDF, then click Find fields.": "ជ្រើសរើស PDF រួចចុច «ស្វែងរកវាល»។", "Click Find fields.": "ចុច «ស្វែងរកវាល»។",
    "Clean Minimal": "សាមញ្ញស្អាត", "Restaurant Menu": "ម៉ឺនុយភោជនីយដ្ឋាន", "Business Card": "ប័ណ្ណអាជីវកម្ម", "Wi-Fi Poster": "ផ្ទាំងប័ទ្ម Wi-Fi",
    "Event Ticket": "សំបុត្រព្រឹត្តិការណ៍", "Social Follow": "តាមដានបណ្តាញសង្គម", "Ocean Gradient": "ក្រឌីយ៉ង់មហាសមុទ្រ",
    "Fresh Green": "បៃតងស្រស់", "Sunset": "ថ្ងៃលិច", "Bold Sticker": "ស្ទីគ័រដិត",
}

_lang = "en"
_SRC, _OUT = "_i18n_src", "_i18n_out"


def language() -> str:
    return _lang


def tr(text: str) -> str:
    """Translate one string for the active language (identity for English / unknown strings)."""
    if _lang != "km" or not text:
        return text
    hit = KM.get(text)
    if hit:
        return hit
    plain = text.replace("&", "")
    if plain in KM:
        return KM[plain]
    m = re.match(r"^(\S)\s\s(.+)$", text, re.S)      # "ⓘ  message" style prefixed advice lines
    if m and m.group(2) in KM:
        return f"{m.group(1)}  {KM[m.group(2)]}"
    return text


def _sync(obj, key: str, current: str, setter) -> None:
    """Remember the English source on `obj` and set the translated (or original) text."""
    prev = obj.property(_SRC + key)
    out = obj.property(_OUT + key)
    src = prev if (prev is not None and current == out) else current      # code changed it -> new source
    new = tr(src)
    if new != current:
        setter(new)
    obj.setProperty(_SRC + key, src)
    obj.setProperty(_OUT + key, new)


def translate_widget(w: QWidget) -> None:
    if isinstance(w, QLabel) and not w.pixmap():
        _sync(w, "t", w.text(), w.setText)
    elif isinstance(w, QAbstractButton):
        _sync(w, "t", w.text(), w.setText)
    if isinstance(w, (QLineEdit, QPlainTextEdit)):
        _sync(w, "p", w.placeholderText(), w.setPlaceholderText)
    if isinstance(w, QComboBox):
        for i in range(w.count()):
            _sync(w, f"c{i}", w.itemText(i), lambda t, i=i: w.setItemText(i, t))
    if w.toolTip():
        _sync(w, "tip", w.toolTip(), w.setToolTip)


def translate_action(a: QAction) -> None:
    _sync(a, "t", a.text(), a.setText)
    if a.toolTip():
        _sync(a, "tip", a.toolTip(), a.setToolTip)
        a.setStatusTip(a.toolTip())


def retranslate(root: QWidget) -> None:
    """Re-apply the active language to `root` and everything inside it (also when switching back to English)."""
    for w in [root, *root.findChildren(QWidget)]:
        translate_widget(w)
    for a in root.findChildren(QAction):
        translate_action(a)
    for m in root.findChildren(QMenu):
        translate_action(m.menuAction())


class _Filter(QObject):
    """Translates widgets that are created later (dialogs, rebuilt panels) the first time they are polished."""

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if _lang != "en" and event.type() == QEvent.Type.Polish and isinstance(obj, QWidget):
            translate_widget(obj)
        return False


_filter: _Filter | None = None


def install(app: QApplication, code: str) -> None:
    global _filter
    if _filter is None:
        _filter = _Filter(app)
        app.installEventFilter(_filter)
    set_language(code)


def set_language(code: str) -> None:
    global _lang
    _lang = code if code in dict(LANGUAGES) else "en"
