# Static Backend Documentation

هذا المشروع عبارة عن backend ثابت (Static API) لتطبيق خلفيات. لا يوجد فيه سيرفر أو قاعدة بيانات أو كود يعمل وقت الطلب؛ الصور وملفات JSON ترفع إلى GitHub، ويستهلكها تطبيق Flutter من خلال روابط GitHub Raw.

## حالة المشروع بعد الفحص

تم فحص المستودع والملفات المولدة محليًا، وكانت النتيجة:

| العنصر | الحالة الحالية |
| --- | ---: |
| الصور المدعومة | 100 صورة |
| التصنيفات | 17 تصنيفًا |
| سجلات الـ API | 100 سجلًا |
| صفحات الـ API | 5 صفحات |
| العناصر في الصفحة | 20 في كل صفحة |
| حجم الصور | 14,619,642 بايت تقريبًا (13.9 MiB) |
| حجم ملفات `api/v1` | 292,837 بايت تقريبًا |
| روابط الصور التي لا تطابق ملفًا محليًا | 0 |
| اختلاف حجم الملف عن metadata | 0 |
| IDs مكررة | 0 |
| روابط مكررة | 0 |
| أبعاد غير مقروءة (`0 × 0`) | 0 |

كل ملفات JSON الحالية قابلة للقراءة، وأعداد التصنيفات في `categories.json` مطابقة لأعداد مجلدات الصور. تمت مراجعة الصور بصريًا في contact sheets وبالحجم الكامل، واستبعاد أي صورة فيها تبغ أو كحول أو مخدرات أو عُري أو إيحاء جنسي صريح أو عنف دموي. الفحص النهائي لا يحتوي على صور مكررة ببصمة SHA-256، وكل الصور المقبولة صالحة للقراءة.

## ملاحظة مهمة قبل النشر أو إعادة التوليد

هوية الإنتاج موحدة على `OmarShawkey13/Wallune`، والفرع المنشور هو `main`. يجب أن تبقى هذه الهوية في ثوابت `generate_api.py` وفي كل `image_url` و`cover` ومرجع API مولد.

## هيكل المشروع

```text
.
├── images/
│   ├── Nature/
│   │   └── image_name.jpg
│   ├── Cars/
│   └── ...
├── api/
│   └── v1/
│       ├── config.json
│       ├── categories.json
│       ├── search_index.json
│       ├── wallpaper_ids.json
│       ├── models.dart
│       └── wallpapers/
│           ├── page_1.json
│           ├── page_2.json
│           └── ...
├── generate_api.py
└── README.md
```

كل مجلد مباشر داخل `images` يعتبر تصنيفًا. اسم الملف يستخدم لتكوين العنوان، مثل `red_bmw_front.jpg` الذي يتحول إلى `Red Bmw Front`.

## طريقة عمل المولد

الملف `generate_api.py` ينفذ الخطوات التالية:

1. يقرأ المجلدات والملفات داخل `images`.
2. يقبل الامتدادات `.jpg` و`.jpeg` و`.png` و`.webp` فقط.
3. يستخرج أبعاد الصورة من الـ binary header بدون مكتبات خارجية.
4. يبني عنوانًا مقروءًا من اسم الملف.
5. ينشئ رابط GitHub Raw مشفرًا للـ category واسم الملف.
6. يحافظ على الـ UUID من خلال بصمة SHA-256 لمحتوى الصورة وملف `wallpaper_ids.json`، مستقلًا عن رابط GitHub.
7. يرتب السجلات حسب التصنيف ثم العنوان.
8. يقسم السجلات إلى صفحات، كل صفحة تحتوي على 20 عنصرًا.
9. يرفض الصور المتطابقة byte-for-byte حتى لا تدخل نسخ مكررة إلى الكتالوج.
10. ينشئ `search_index.json` و`categories.json` و`config.json` و`wallpaper_ids.json` و`models.dart`.
11. يكتب الناتج في staging، ثم يستبدل الملفات المولدة مع backup وrollback عند الفشل.
12. يشغّل validator قبل الاستبدال وبعده، ويتأكد من bytes الصورة الفعلية وhash والأبعاد والحجم والـ IDs والـ aliases.

الإعدادات الرئيسية الموجودة في بداية الملف:

```python
IMAGE_DIR = 'images'
API_DIR = 'api/v1'
GITHUB_USERNAME = 'OmarShawkey13'
GITHUB_REPO_NAME = 'Wallune'
BRANCH = 'main'
ITEMS_PER_PAGE = 20
```

## ملفات الـ API

### التصنيفات

الرابط:

```text
<BASE_URL>/api/v1/categories.json
```

الاستجابة عبارة عن array:

```json
[
  {
    "id": "uuid",
    "name": "Nature",
    "count": 26,
    "cover": "https://raw.githubusercontent.com/OmarShawkey13/Wallune/main/images/Nature/cover.jpg"
  }
]
```

- `id`: UUID حتمي مشتق من اسم التصنيف ويظل ثابتًا بين عمليات التوليد.
- `name`: اسم المجلد والتصنيف.
- `count`: عدد الصور المدعومة داخل التصنيف.
- `cover`: رابط أول صورة في التصنيف حسب ترتيب قراءة الملفات أثناء التوليد.

### فهرس البحث

الرابط:

```text
<BASE_URL>/api/v1/search_index.json
```

الفهرس خفيف ومناسب للبحث المحلي داخل التطبيق، ويحتوي على كل metadata اللازمة لعرض النتيجة بدون lookup إضافي:

```json
[
  {
    "id": "uuid",
    "title": "Snowy Mountain Sunset",
    "category": "Nature",
    "image_url": "https://raw.githubusercontent.com/OmarShawkey13/Wallune/main/images/Nature/snowy_mountain_sunset.jpg",
    "size": 123456,
    "updated_at": "2026-09-15T10:30:45Z",
    "width": 864,
    "height": 1536
  }
]
```

الفهرس لا يحتوي على bytes للصورة، وحجمه الحالي حوالي 30 KB. يجب أن يطابق كل سجل في الفهرس السجل الموجود في الصفحات حرفيًا في الحقول العامة.

### إعدادات الـ API

الرابط:

```text
<BASE_URL>/api/v1/config.json
```

يحتوي على `api_version` و`content_version` و`total_items` و`total_pages` و`items_per_page` و`generated_at` و`catalog_hash`. يحتفظ المولد بنفس `content_version` إذا لم يتغير catalog، ويزيده عند تغيره. يحتوي `models.dart` أيضًا على `ApiConfig` لقراءة هذا الملف.

### صفحات الخلفيات

الرابط:

```text
<BASE_URL>/api/v1/wallpapers/page_1.json
```

شكل الاستجابة:

```json
{
  "page": 1,
  "total_pages": 5,
  "total_items": 100,
  "items_per_page": 20,
  "has_next": true,
  "has_prev": false,
  "data": [
    {
      "id": "uuid",
      "title": "Birds On Red Sky",
      "category": "Nature",
      "image_url": "https://raw.githubusercontent.com/OmarShawkey13/Wallune/main/images/Nature/birds_on_red_sky.jpg",
      "size": 56101,
      "updated_at": "2026-10-12T11:39:33Z",
      "width": 864,
      "height": 1536
    }
  ]
}
```

حقول `data`:

| الحقل | النوع | الاستخدام |
| --- | --- | --- |
| `id` | string | معرف ثابت نسبيًا للمفضلة والربط داخل التطبيق |
| `title` | string | عنوان العرض الناتج من اسم الملف |
| `category` | string | التصنيف |
| `image_url` | string | رابط الصورة على GitHub Raw |
| `size` | integer | حجم الملف بالبايت |
| `updated_at` | string | وقت تثبيت هوية الصورة؛ محفوظ في metadata ولا يتغير مع mtime |
| `width` / `height` | integer | أبعاد الصورة بالبكسل |

## الاستخدام في Flutter

انسخ `api/v1/models.dart` إلى مشروع Flutter، ثم استخدم صفحة API:

```dart
import 'dart:convert';
import 'package:http/http.dart' as http;
import 'models.dart';

const apiBase =
    'https://raw.githubusercontent.com/OmarShawkey13/Wallune/main/api/v1';

Future<PaginatedResponse> fetchWallpapers(int page) async {
  final response = await http.get(
    Uri.parse('$apiBase/wallpapers/page_$page.json'),
  );

  if (response.statusCode != 200) {
    throw Exception('Failed to load wallpapers: ${response.statusCode}');
  }

  return PaginatedResponse.fromJson(
    jsonDecode(response.body) as Map<String, dynamic>,
  );
}
```

استخدم `width` و`height` مع `flutter_staggered_grid_view` لتقليل layout jumps، واستخدم `updated_at` أو `id` مع caching والمفضلة.

## التشغيل والتحديث

بعد تثبيت Python 3:

```bash
python generate_api.py
```

أو على Windows إذا كان Python Launcher متوفرًا:

```bash
py generate_api.py
```

خطوات التحديث المقترحة:

1. ضع الصور داخل مجلد تصنيف موجود أو أنشئ مجلدًا جديدًا.
2. تأكد من أن الامتداد واحد من الامتدادات المدعومة.
3. وحّد `GITHUB_USERNAME` و`GITHUB_REPO_NAME` و`BRANCH` مع مستودع GitHub الفعلي.
4. شغّل `generate_api.py` من جذر المشروع.
5. راجع عدد السجلات والصفحات والروابط قبل commit.
6. ارفع `images` و`api/v1` و`generate_api.py` إلى الفرع المنشور.

للفحص فقط بدون تعديل أي ملف:

```bash
python generate_api.py --validate-only
```

قبل كتابة الصفحات، يجهز المولد كل الملفات داخل مجلد staging، ثم ينقلها إلى `api/v1` بعد أخذ نسخة احتياطية من الملفات المولدة. إذا فشل النقل أو التحقق يعيد الملفات السابقة. هذا rollback لكل ملف مولد، وليس ادعاءً بأن تبديل المجلد كاملًا atomic على كل أنظمة الملفات. يحذف فقط الملفات المطابقة للنمط `page_<number>.json`، ثم ينشئ العدد الجديد بالضبط؛ الملفات الأخرى داخل المجلد لا تُلمس.

## قواعد الحفاظ على الـ IDs

يتم حفظ الـ UUID في `api/v1/wallpaper_ids.json` اعتمادًا على SHA-256 لمحتوى الصورة، مع aliases للمسارات السابقة وtombstones للعناصر المحذوفة. لذلك:

- إعادة التوليد يحافظ على `id` لنفس bytes الصورة.
- تغيير اسم الملف أو التصنيف أو repository أو branch لا يغير `id` طالما بقي محتوى الصورة نفسه.
- تغيير bytes الصورة في نفس المسار ينشئ `id` جديدًا ويحوّل الـ ID القديم إلى retired tombstone.
- بعد وجود `wallpaper_ids.json` تصبح metadata هي المصدر authoritative؛ لا يعيد المولد بناء الهوية من صفحات قديمة، ويرفض metadata الفارغة إذا كانت صفحات legacy تحتوي IDs حتى لا يعيد تعيين الهوية.
- `updated_at` محفوظ داخل metadata. أثناء migration تُحفظ قيمة legacy الصحيحة، والقيمة الناقصة أو غير الصالحة تستخدم fallback ثابتًا `2000-01-01T00:00:00Z` حتى لا تتغير timestamps بسبب mtime.
- الصور المتطابقة byte-for-byte مرفوضة أثناء التوليد حتى لا تدخل نسخ مكررة إلى الكتالوج.
- الصور الجديدة تحصل على UUID جديد، والعناصر المحذوفة تبقى tombstones ولا يعاد استخدام IDs الخاصة بها.
- لا تحذف `wallpaper_ids.json` لأنه جزء من هوية البيانات.

## التحقق والاختبارات

`validate_generated_api()` يعمل للقراءة فقط ويتأكد من أن أسماء الصفحات هي `page_1.json` حتى `page_N.json` بلا فجوات أو صفحات زائدة، وأن رقم الصفحة داخل JSON يطابق اسمها. كما يقارن السجلات بالصور المحلية فعليًا: حجم الملف، الأبعاد، وSHA-256، ثم يطابق الـ IDs النشطة والـ aliases مع `wallpaper_ids.json`. ويتحقق من عدم وجود IDs أو URLs مكررة، اكتمال `search_index.json`، صحة category IDs والأعداد والـ covers، وصحة `catalog_hash` وحقول pagination وUTC timestamps.

الاختبارات المعزولة داخل `tests/test_generate_api.py` تستخدم صور JPEG وPNG وWebP صحيحة و26 حالة regression. وهي تغطي استبدال bytes، rename، retired IDs، فساد وفراغ metadata، migration وfallback للـ timestamps، ثبات timestamps، تغيير pagination و`content_version`، أخطاء الحجم والأبعاد والhash، فجوات الصفحات، duplicate search rows، فشل الكتابة والrollback بعد الاستبدال، و`--validate-only` بدون أي كتابة.

## حدود وملاحظات تشغيلية

- هذا backend لا يوفر authentication أو صلاحيات أو رفع ملفات أو filtering server-side أو rate limiting.
- الاعتماد على GitHub Raw يعني أن توفر الخدمة والـ caching وسرعة التنزيل تابعة لـ GitHub.
- المستودع عام عمليًا لكل من يملك الرابط؛ لا تضع أسرارًا أو بيانات خاصة في الصور أو JSON.
- `updated_at` و`generated_at` يستخدمان UTC مع `Z`. `updated_at` للهوية لا يعاد توليده عند تغيير mtime أو إعادة التسمية.
- `models.dart` مولد تلقائيًا؛ لا تعدله يدويًا، وأي تعديل على schema يجب أن ينعكس في `generate_dart_models`.
- المصدر المنشور الوحيد هو `api/v1`؛ لا يتم إنشاء ملف monolithic باسم `wallpapers.json`.
- الصور تتضمن محتوى لشخصيات وعلامات تجارية وأعمال فنية. راجع حقوق الاستخدام والترخيص قبل النشر العام.

## قائمة تحقق قبل GitHub

```text
[ ] اسم repository والـ branch في generator يطابقان مكان الرفع.
[ ] كل صورة داخل category واضح وبامتداد مدعوم.
[ ] عدد الصور يساوي total_items ويساوي مجموع counts.
[ ] لا توجد صفحات قديمة بعد آخر page_N.
[ ] روابط image_url وcover تشير إلى repository الصحيح.
[ ] تم اختبار config.json وcategories.json وsearch_index.json وصفحة أولى وصفحة أخيرة.
[ ] تم تشغيل `python generate_api.py --validate-only` بعد التوليد.
[ ] تم التأكد من حقوق استخدام الصور.
[ ] تم تشغيل git diff قبل commit.
```
