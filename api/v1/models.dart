// AUTO-GENERATED CODE - DO NOT MODIFY BY HAND
// Wallune static API models.

class Wallpaper {
  final String id;
  final String title;
  final String category;
  final String imageUrl;
  final int size;
  final String updatedAt;
  final int width;
  final int height;

  Wallpaper({
    required this.id,
    required this.title,
    required this.category,
    required this.imageUrl,
    required this.size,
    required this.updatedAt,
    required this.width,
    required this.height,
  });

  factory Wallpaper.fromJson(Map<String, dynamic> json) => Wallpaper(
    id: json['id'] as String? ?? '',
    title: json['title'] as String? ?? '',
    category: json['category'] as String? ?? '',
    imageUrl: json['image_url'] as String? ?? '',
    size: (json['size'] as num?)?.toInt() ?? 0,
    updatedAt: json['updated_at'] as String? ?? '',
    width: (json['width'] as num?)?.toInt() ?? 0,
    height: (json['height'] as num?)?.toInt() ?? 0,
  );

  Map<String, dynamic> toJson() => {
    'id': id, 'title': title, 'category': category, 'image_url': imageUrl,
    'size': size, 'updated_at': updatedAt, 'width': width, 'height': height,
  };
}

class PaginatedResponse {
  final int page;
  final int totalPages;
  final int totalItems;
  final int itemsPerPage;
  final bool hasNext;
  final bool hasPrev;
  final List<Wallpaper> data;

  PaginatedResponse({
    required this.page,
    required this.totalPages,
    required this.totalItems,
    required this.itemsPerPage,
    required this.hasNext,
    required this.hasPrev,
    required this.data,
  });

  factory PaginatedResponse.fromJson(Map<String, dynamic> json) => PaginatedResponse(
    page: (json['page'] as num?)?.toInt() ?? 0,
    totalPages: (json['total_pages'] as num?)?.toInt() ?? 0,
    totalItems: (json['total_items'] as num?)?.toInt() ?? 0,
    itemsPerPage: (json['items_per_page'] as num?)?.toInt() ?? 20,
    hasNext: json['has_next'] as bool? ?? false,
    hasPrev: json['has_prev'] as bool? ?? false,
    data: ((json['data'] as List?) ?? const [])
        .map((item) => Wallpaper.fromJson(item as Map<String, dynamic>))
        .toList(),
  );
}

class Category {
  final String name;
  final int count;
  final String cover;

  Category({required this.name, required this.count, required this.cover});

  factory Category.fromJson(Map<String, dynamic> json) => Category(
    name: json['name'] as String? ?? '',
    count: (json['count'] as num?)?.toInt() ?? 0,
    cover: json['cover'] as String? ?? '',
  );
}

class ApiConfig {
  final int apiVersion;
  final int contentVersion;
  final int totalItems;
  final int totalPages;
  final int itemsPerPage;
  final String generatedAt;
  final String catalogHash;

  ApiConfig({
    required this.apiVersion,
    required this.contentVersion,
    required this.totalItems,
    required this.totalPages,
    required this.itemsPerPage,
    required this.generatedAt,
    required this.catalogHash,
  });

  factory ApiConfig.fromJson(Map<String, dynamic> json) => ApiConfig(
    apiVersion: (json['api_version'] as num?)?.toInt() ?? 1,
    contentVersion: (json['content_version'] as num?)?.toInt() ?? 0,
    totalItems: (json['total_items'] as num?)?.toInt() ?? 0,
    totalPages: (json['total_pages'] as num?)?.toInt() ?? 0,
    itemsPerPage: (json['items_per_page'] as num?)?.toInt() ?? 20,
    generatedAt: json['generated_at'] as String? ?? '',
    catalogHash: json['catalog_hash'] as String? ?? '',
  );
}
