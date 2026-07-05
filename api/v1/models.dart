// AUTO-GENERATED CODE - DO NOT MODIFY BY HAND
// Use this code in your Flutter app to easily parse the Wallune API

import 'dart:convert';

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

  factory Wallpaper.fromJson(Map<String, dynamic> json) {
    return Wallpaper(
      id: json['id'] ?? '',
      title: json['title'] ?? '',
      category: json['category'] ?? '',
      imageUrl: json['image_url'] ?? '',
      size: json['size'] ?? 0,
      updatedAt: json['updated_at'] ?? '',
      width: json['width'] ?? 0,
      height: json['height'] ?? 0,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'title': title,
      'category': category,
      'image_url': imageUrl,
      'size': size,
      'updated_at': updatedAt,
      'width': width,
      'height': height,
    };
  }
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

  factory PaginatedResponse.fromJson(Map<String, dynamic> json) {
    return PaginatedResponse(
      page: json['page'] ?? 1,
      totalPages: json['total_pages'] ?? 1,
      totalItems: json['total_items'] ?? 0,
      itemsPerPage: json['items_per_page'] ?? 20,
      hasNext: json['has_next'] ?? false,
      hasPrev: json['has_prev'] ?? false,
      data:
          (json['data'] as List?)?.map((e) => Wallpaper.fromJson(e)).toList() ??
          [],
    );
  }
}

class Category {
  final String name;
  final int count;
  final String cover;

  Category({required this.name, required this.count, required this.cover});

  factory Category.fromJson(Map<String, dynamic> json) {
    return Category(
      name: json['name'] ?? '',
      count: json['count'] ?? 0,
      cover: json['cover'] ?? '',
    );
  }
}
