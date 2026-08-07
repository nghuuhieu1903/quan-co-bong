#!/usr/bin/env python3
"""
Script to add sample rooms to the database
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app, db, Room
import json

def add_sample_rooms():
    """Add sample rooms to the database"""
    
    sample_rooms = [
        {
            'name': 'Phòng Standard 1',
            'description': 'Phòng tiêu chuẩn với đầy đủ tiện nghi cơ bản, phù hợp cho khách du lịch cá nhân hoặc cặp đôi.',
            'price_per_hour': 50000,
            'capacity': 2,
            'image': 'pngtree.png',
            'amenities': json.dumps(['WiFi', 'Điều hòa', 'TV', 'Giường đôi', 'Bàn làm việc']),
            'available': True
        },
        {
            'name': 'Phòng Deluxe 2',
            'description': 'Phòng cao cấp với không gian rộng rãi, view nhìn đẹp, trang bị nội thất sang trọng.',
            'price_per_hour': 80000,
            'capacity': 3,
            'image': 'pngtree.png',
            'amenities': json.dumps(['WiFi tốc độ cao', 'Điều hòa', 'Smart TV 43 inch', 'Mini bar', 'Bàn làm việc', 'Giường king size', 'Ban công']),
            'available': True
        },
        {
            'name': 'Phòng Family 3',
            'description': 'Phòng gia đình rộng rãi, có khu vực ngồi riêng, phù hợp cho gia đình hoặc nhóm bạn.',
            'price_per_hour': 120000,
            'capacity': 5,
            'image': 'pngtree.png',
            'amenities': json.dumps(['WiFi', 'Điều hòa', 'TV 50 inch', 'Sofa', 'Bàn ăn', 'Khu vực bếp nhỏ', '2 giường', 'Tủ lạnh']),
            'available': True
        },
        {
            'name': 'Phòng Economy 4',
            'description': 'Phòng tiết kiệm chi phí với tiện nghi cơ bản, lý tưởng cho khách du lịch bụi.',
            'price_per_hour': 35000,
            'capacity': 1,
            'image': 'pngtree.png',
            'amenities': json.dumps(['WiFi', 'Quạt', 'Giường đơn', 'Tủ đồ']),
            'available': True
        },
        {
            'name': 'Phòng Business 5',
            'description': 'Phòng dành cho doanh nhân với không gian làm việc chuyên nghiệp và tiện nghi hiện đại.',
            'price_per_hour': 100000,
            'capacity': 2,
            'image': 'pngtree.png',
            'amenities': json.dumps(['WiFi tốc độ cao', 'Điều hòa', 'Smart TV', 'Bàn làm việc lớn', 'Máy in', 'Giường đôi', 'Két sắt']),
            'available': False  # Đang bảo trì
        },
        {
            'name': 'Phòng Studio 6',
            'description': 'Phòng studio hiện đại với thiết kế tối giản, không gian mở và đầy đủ tiện nghi.',
            'price_per_hour': 90000,
            'capacity': 4,
            'image': 'pngtree.png',
            'amenities': json.dumps(['WiFi', 'Điều hòa', 'TV', 'Khu vực bếp', 'Bàn ăn', 'Sofa bed', 'Máy giặt']),
            'available': True
        }
    ]
    
    with app.app_context():
        # Check if rooms already exist
        existing_rooms = Room.query.count()
        if existing_rooms > 0:
            print(f"Đã có {existing_rooms} phòng trong database. Bạn có muốn thêm phòng mẫu không? (y/n)")
            response = input().strip().lower()
            if response != 'y':
                print("Không thêm phòng mẫu.")
                return
        
        # Add sample rooms
        added_count = 0
        for room_data in sample_rooms:
            # Check if room with same name already exists
            existing = Room.query.filter_by(name=room_data['name']).first()
            if existing:
                print(f"Phòng '{room_data['name']}' đã tồn tại, bỏ qua.")
                continue
            
            room = Room(**room_data)
            db.session.add(room)
            added_count += 1
        
        try:
            db.session.commit()
            print(f"Đã thêm thành công {added_count} phòng mẫu vào database!")
            
            # Display added rooms
            print("\nDanh sách phòng đã thêm:")
            for room_data in sample_rooms:
                existing = Room.query.filter_by(name=room_data['name']).first()
                if existing:
                    status = "✓" if existing.available else "✗ (Đang bảo trì)"
                    print(f"- {existing.name}: {existing.price_per_hour:,.0f} VNĐ/giờ - {existing.capacity} người {status}")
                    
        except Exception as e:
            db.session.rollback()
            print(f"Lỗi khi thêm phòng mẫu: {e}")

if __name__ == '__main__':
    add_sample_rooms()
