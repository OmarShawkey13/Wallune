# دليل Wallune Static Backend

هذا المستودع هو مصدر المحتوى الثابت لتطبيق Wallune. الصور وملفات JSON المولدة تُرفع إلى GitHub، وتقرأها نسخة Flutter من خلال GitHub Raw. لا يوجد سيرفر أو قاعدة بيانات أو نظام تسجيل دخول أو endpoint للرفع.

## رابط الـ API

```text
https://raw.githubusercontent.com/OmarShawkey13/Wallune/main/api/v1
```

| الملف | الاستخدام |
| --- | --- |
| `config.json` | إصدار الـ API وإصدار الكتالوج والأعداد و`catalog_hash` |
| `categories.json` | التصنيفات ومعرّف كل تصنيف وعدده وصورة الغلاف |
| `search_index.json` | بيانات خفيفة للبحث المحلي |
| `wallpapers/page_N.json` | السجلات الأساسية مقسمة إلى صفحات |

## هيكل المشروع

```text
images/                         الصور المعتمدة
  <Category>/<name>.jpg
api/v1/                         مخرجات الـ API المولدة
  config.json
  categories.json
  search_index.json
  wallpaper_ids.json
  wallpapers/page_*.json
generate_api.py                 المولد والـ validator
tests/test_generate_api.py      اختبارات regression
```

المجلد `new_wall/` مساحة محلية مؤقتة للدفعات الجديدة، وهو متجاهل في Git. تتم مراجعة الصور داخله أولًا، ثم تُنقل الصور المقبولة فقط إلى التصنيف المناسب داخل `images/`.

## شكل البيانات

كل wallpaper يحتوي على:

- `id`: UUID ثابت للمفضلة والربط داخل التطبيق.
- `title`: عنوان العرض الناتج من اسم الملف.
- `category`: اسم مجلد التصنيف.
- `image_url`: رابط GitHub Raw مشفّر بشكل صحيح.
- `size`: حجم الملف بالبايت.
- `updated_at`: وقت إنشاء هوية الصورة، محفوظ في سجل الهوية.
- `width` و`height`: أبعاد الصورة الأصلية.

كل category يحتوي على `id` حتمي مشتق من اسمه، بالإضافة إلى `name` و`count` و`cover`. ملف `wallpaper_ids.json` هو سجل الهوية الرسمي؛ يحتفظ بالـ IDs المتقاعدة كـ tombstones حتى لا يُعاد استخدام ID قديم لصورة مختلفة.

## طريقة تحديث الصور

1. ضع الدفعة الجديدة في `new_wall/`.
2. راجع المحتوى بصريًا واحذف الصور المخالفة أو غير المناسبة والمكررة.
3. استخدم أسماء lowercase بصيغة `snake_case` وانقل الصور المقبولة إلى `images/<Category>/`.
4. شغّل المولد من جذر المشروع:

   ```bash
   python generate_api.py
   ```

   في Windows يمكن استخدام `py -3 generate_api.py`.

5. شغّل الاختبارات:

   ```bash
   python -m unittest discover -s tests -v
   ```

6. نفّذ فحصًا نهائيًا بدون كتابة:

   ```bash
   python generate_api.py --validate-only
   ```

المولد يفحص الامتداد والأبعاد والحجم وSHA-256، يحافظ على الـ IDs، ينشئ الملفات داخل staging، يتحقق منها، ثم يستبدل المخرجات مع rollback عند الفشل. يحذف فقط صفحات `page_<number>.json` القديمة؛ لا يلمس الملفات الأخرى داخل مجلد الصفحات.

## الحالة الحالية

| العنصر | القيمة |
| --- | ---: |
| الصور المدعومة | 453 |
| التصنيفات | 17 |
| صفحات الـ API | 23 |
| العناصر في الصفحة | 20 |
| العناصر في الصفحة الأخيرة | 13 |
| حجم الصور | 61,850,981 بايت تقريبًا (59 MiB) |
| الـ IDs النشطة | 453 |
| سجلات الـ IDs المتقاعدة | 627 |

الفحص الحالي يطابق كل صورة محلية مع سجل API واحد، ولا توجد بصمات SHA-256 مكررة أو IDs نشطة مكررة أو صفحات ناقصة أو روابط صور محلية مكسورة.

## استخدام Flutter

```dart
const apiBase =
    'https://raw.githubusercontent.com/OmarShawkey13/Wallune/main/api/v1';

final response = await http.get(
  Uri.parse('$apiBase/wallpapers/page_1.json'),
);
```

استخدم `content_version` لتحديد وقت تحديث الكاش، و`id` للمفضلة، و`width` و`height` لتقليل تغيّر تخطيط الشبكة أثناء تحميل الصور. اعتبر أخطاء الشبكة وملفات JSON غير الصالحة والصور غير المتاحة حالات قابلة لإعادة المحاولة.

## حدود الاستضافة

GitHub Raw استضافة عامة وثابتة؛ لا يوفر authentication أو uploads أو filtering على الخادم أو rate limiting مضمونًا. يجب مراجعة ترخيص أي صورة جديدة قبل نشرها.
