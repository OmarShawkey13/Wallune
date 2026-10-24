# دليل Wallune Static Backend

هذا المستودع هو مصدر المحتوى الثابت لتطبيق Wallune. الصور وملفات JSON المصغرة تُرفع إلى GitHub، وتقرأها نسخة Flutter من خلال GitHub Raw. لا يوجد سيرفر أو قاعدة بيانات أو نظام تسجيل دخول أو endpoint للرفع. المولد يستخدم مكتبة Pillow لإنشاء صور WebP المصغرة؛ ثبّتها مرة واحدة باستخدام `python -m pip install -r requirements.txt`.

## رابط الـ API

```text
https://raw.githubusercontent.com/OmarShawkey13/Wallune/main/api/v1
```

| الملف | الاستخدام |
| --- | --- |
| `config.json` | إصدارات الـ API ومخططات البيانات والكتالوج، الأعداد و`catalog_hash` |
| `categories.json` | التصنيفات ومعرّف كل تصنيف وعدده وصورة الغلاف |
| `search_index.json` | فهرس بحث محلي مختصر بإصدار schema 3 |
| `wallpapers/page_N.json` | السجلات الأساسية مقسمة إلى صفحات |

## هيكل المشروع

```text
images/                         الصور المعتمدة
  <Category>/<name>.jpg
api/v1/                         مخرجات الـ API المولدة
  config.json
  categories.json
  search_index.json
  thumbnails/                   صور WebP مصغرة لكل خلفية
  wallpapers/page_*.json
generate_api.py                 المولد والـ validator
tests/test_generate_api.py      اختبارات regression
requirements.txt                مكتبة معالجة الصور للمولد
```

المجلد `new_wall/` مساحة محلية مؤقتة للدفعات الجديدة، وهو متجاهل في Git. تتم مراجعة الصور داخله أولًا، ثم تُنقل الصور المقبولة فقط إلى التصنيف المناسب داخل `images/`.

## شكل البيانات

كل wallpaper يحتوي على:

- `id`: UUID ثابت مشتق من محتوى الصورة؛ المولد يستخدمه لربط السجل بالـthumbnail.
- `title`: عنوان العرض الناتج من اسم الملف.
- `category`: اسم مجلد التصنيف.
- `image_url`: رابط GitHub Raw مشفّر بشكل صحيح.
- `thumbnail_url`: رابط نسخة WebP خفيفة للشبكة ونتائج البحث.
- `size`: حجم الملف بالبايت.
- `updated_at`: وقت إضافة محتوى الصورة للكتالوج؛ يُحفظ عند تطابق معرّف المحتوى مع السجل السابق. في أول ترحيل من IDs عشوائية، يُحدّث التاريخ لأن السجل القديم لا يحتوي على hash يثبت تطابق ملف الصورة.
- `width` و`height`: أبعاد الصورة الأصلية.

معرّف wallpaper هو UUID حتمي مشتق من SHA-256 لمحتوى الصورة، لذلك يظل ثابتًا عند تغيير اسم الملف أو التصنيف. إصدار طريقة إنشاء الـIDs ظاهر في `wallpaper_id_version` داخل `config.json`، ولا يحتاج المولد إلى ملف سجل منفصل. كل category يحتوي على `id` حتمي مشتق من اسمه، بالإضافة إلى `name` و`count` و`cover` للصورة الأصلية و`cover_thumbnail_url` للنسخة المصغرة.

## طريقة تحديث الصور

1. ضع الدفعة الجديدة في `new_wall/`.
2. راجع المحتوى بصريًا واحذف الصور المخالفة أو غير المناسبة والمكررة.
3. استخدم أسماء lowercase بصيغة `snake_case` وانقل الصور المقبولة إلى `images/<Category>/`.
4. ثبّت مكتبة المولد مرة واحدة:

   ```bash
   python -m pip install -r requirements.txt
   ```

5. شغّل المولد من جذر المشروع:

   ```bash
   python generate_api.py
   ```

   في Windows يمكن استخدام `py -3 generate_api.py`.

6. شغّل الاختبارات:

   ```bash
   python -m unittest discover -s tests -v
   ```

7. نفّذ فحصًا نهائيًا بدون كتابة:

   ```bash
   python generate_api.py --validate-only
   ```

المولد يفحص الصور وأبعادها وSHA-256، ويحافظ على الـ IDs. يكتب JSON في staging ويعيد استخدام أي thumbnail سليمة موجودة لنفس الـ ID؛ يعيد إنشاء الناقص أو التالف فقط. بعدها يستبدل المخرجات، يتحقق من النسخة النهائية، ويرجع النسخة السابقة إذا فشل التحقق. الملفات المولدة القديمة تُحذف مع الحفاظ على الملفات الأخرى.

## الحالة الحالية

| العنصر | القيمة |
| --- | ---: |
| الصور المدعومة | 1,269 |
| التصنيفات | 17 |
| صفحات الـ API | 64 |
| العناصر في الصفحة | 20 |
| العناصر في الصفحة الأخيرة | 9 |
| حجم الصور الأصلية | 198,872,143 بايت تقريبًا (189.7 MiB) |
| الصور المصغرة المولدة | 1,269 بحجم 50,176,100 بايت تقريبًا (47.9 MiB) |
| حجم `search_index.json` | 487,306 بايت؛ المتوقع خطيًا نحو 3.84 MB عند 10,000 صورة |
| إصدار schema البحث | 3 |
| الـ IDs النشطة | 1,269 |

الفحص الحالي يطابق كل صورة محلية مع سجل API ونسخة مصغرة، ولا توجد بصمات SHA-256 مكررة أو IDs نشطة مكررة أو صفحات وصور مصغرة ناقصة أو روابط صور محلية مكسورة.

## استخدام Flutter

```dart
const apiBase =
    'https://raw.githubusercontent.com/OmarShawkey13/Wallune/main/api/v1';

final response = await http.get(
  Uri.parse('$apiBase/wallpapers/page_1.json'),
);
```

استخدم `thumbnail_url` في شبكة الخلفيات و`cover_thumbnail_url` لأغلفة التصنيفات، و`image_url` في صفحة التفاصيل أو التنزيل. يحتوي `search_index.json` على `id` و`title` و`category` و`image_url` و`thumbnail_url` و`width` و`height` فقط. أسماء حقول الروابط وقيمها مطابقة لسجلات الصفحات؛ لا تحتاج إلى تحويل المسارات:

```dart
final previewUri = Uri.parse(result['thumbnail_url'] as String);
final imageUri = Uri.parse(result['image_url'] as String);
```

استخدم سجل الصفحة لجلب الحجم ووقت التحديث عند الحاجة. خزّن `config.json` و`search_index.json` والصفحات والصور المصغرة مؤقتًا، وجدّد بيانات الكتالوج فقط عند تغيّر `content_version`. استخدم `id` للمفضلة و`width` و`height` لتقليل تغيّر تخطيط الشبكة أثناء تحميل الصور. اعتبر أخطاء الشبكة وملفات JSON غير الصالحة والصور غير المتاحة حالات قابلة لإعادة المحاولة.

## حدود الاستضافة

GitHub Raw استضافة عامة وثابتة؛ لا يوفر authentication أو uploads أو filtering على الخادم أو rate limiting مضمونًا. يجب مراجعة ترخيص أي صورة جديدة قبل نشرها.
