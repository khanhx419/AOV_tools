# Hướng Dẫn Sử Dụng AOV Tools (Tool Auto Liên Quân Mobile)

## 1. Yêu cầu hệ thống
- **Hệ điều hành**: Windows.
- **Python**: Phiên bản 3.10 trở lên.
- **LDPlayer**: Khuyên dùng phiên bản LDPlayer 9.
- **Tesseract OCR**: Cần cài đặt phần mềm này để nhận diện ký tự chữ số (đọc ID Phòng).

---

## 2. Cài đặt môi trường

### 2.1. Cài đặt Python & Thư viện
1. Mở Command Prompt (cmd) hoặc PowerShell.
2. Di chuyển đến thư mục chứa mã nguồn:
   ```bash
   cd C:\Users\Admin\Desktop\code\AOV_tools
   ```
3. Cài đặt các thư viện cần thiết:
   ```bash
   pip install -r requirements.txt
   ```

### 2.2. Cài đặt Tesseract OCR
1. Tải Tesseract OCR cho Windows từ [UB-Mannheim Tesseract Wiki](https://github.com/UB-Mannheim/tesseract/wiki).
2. Chạy file cài đặt. Hãy ghi nhớ đường dẫn cài đặt (mặc định thường là `C:\Program Files\Tesseract-OCR`).
3. **(Rất Quan trọng)**: Thêm thư mục `C:\Program Files\Tesseract-OCR` vào biến môi trường **PATH** của Windows để Python có thể gọi phần mềm này.

---

## 3. Chuẩn bị hình ảnh mẫu (Templates)
Tool sử dụng công nghệ nhận diện hình ảnh (OpenCV) để tìm nút bấm. Bạn **BẮT BUỘC** phải chụp ảnh màn hình các nút bấm trong game, cắt nhỏ chúng (chỉ lấy gọn phần hình ảnh của nút/icon), và lưu thành các file định dạng `.png` vào thư mục `templates/`.

> **Lưu ý cực kỳ quan trọng**: Game trên tất cả các giả lập phải được cài đặt cùng 1 độ phân giải (Khuyên dùng: `1280x720` hoặc `960x540`) để tool nhận diện được chính xác nhất. Khi cắt ảnh, hãy cắt trên chính màn hình giả lập đó.

Dưới đây là danh sách tên các file hình ảnh bạn cần chuẩn bị trong thư mục `templates/`:

**Phase 1 (Nhận thưởng & Cửa hàng)**
- `reward_claim.png`: Nút nhận thưởng (các dấu chấm đỏ hoặc nút nhận).
- `shop_icon.png`: Biểu tượng cửa hàng.
- `item_buy.png`: Nút mua vật phẩm trong shop.
- `backpack_icon.png`: Biểu tượng túi đồ ở màn hình chính.
- `item_use.png`: Nút sử dụng vật phẩm trong túi đồ.
- `main_screen.png`: Một góc/đặc điểm nhận dạng của màn hình chính để tool biết đã quay lại sảnh.
- `close_popup.png`: Nút tắt (dấu X) của các popup quảng cáo lúc mới vào game (dùng để xử lý lỗi kẹt màn hình).

**Phase 2 (Tạo/Vào phòng)**
- `custom_mode.png`: Nút chế độ đấu luyện / phòng tùy chọn.
- `create_room.png`: Nút tạo phòng.
- `join_room.png`: Nút vào phòng (dành cho Slave).
- `room_lobby.png`: Đặc điểm nhận dạng khi đã vào trong sảnh chờ của phòng.
- `room_id_input.png`: Khung nhập ID phòng.
- `confirm_join.png`: Nút xác nhận sau khi nhập ID phòng.

**Phase 3 (Trong trận)**
- `hero_select.png`: Khung ảnh của tướng cần chọn.
- `ready_btn.png`: Nút "Sẵn sàng" / "Khóa tướng".
- `battlefield.png`: Đặc điểm nhận dạng khi đã load xong vào trận đấu (VD: bản đồ thu nhỏ, icon kỹ năng).
- `feature_icon.png`: Nút tính năng cần bấm lúc 3 phút.
- `feature_toggle_on.png`: Đặc điểm nhận dạng khi tính năng ĐANG BẬT.
- `feature_toggle_off.png`: Đặc điểm nhận dạng khi tính năng ĐANG TẮT.
- `victory.png` / `defeat.png` / `match_result.png`: Các chữ Chiến Thắng, Thất Bại hoặc màn hình kết quả chung.
- `continue_btn.png`: Nút "Tiếp tục" ở màn hình kết quả.
- `play_again.png`: Nút "Chơi lại".
- `exit_room.png`: Nút thoát phòng (để dùng sau khi kết thúc trận cuối cùng).

---

## 4. Cấu hình Tool (`config.json`)
Mở file `config.json` bằng Notepad hoặc VS Code và chỉnh sửa các thông số cho phù hợp với máy của bạn.

| Tham số | Ý nghĩa |
|---------|---------|
| `ldplayer_path` | Đường dẫn tới thư mục cài đặt LDPlayer (Mặc định: `C:\\LDPlayer\\LDPlayer9`). |
| `adb_path` | Đường dẫn tới file `adb.exe` của LDPlayer (Mặc định: `C:\\LDPlayer\\LDPlayer9\\adb.exe`). |
| `resolution` | Độ phân giải giả lập đang thiết lập. |
| `instance_groups` | Phân chia nhóm Master - Slave. `master` là Index của giả lập chủ phòng (Tạo phòng). `slaves` là mảng các Index của giả lập vào phòng. *(Index có thể xem ở cột ngoài cùng bên trái trong LDMultiPlayer, bắt đầu từ 0)*. |
| `match_count` | Số lượng trận đấu sẽ lặp lại (Mặc định: 4). |
| `match_timer_seconds` | Thời gian chờ (giây) kể từ lúc vào trận cho đến khi bấm tính năng (Mặc định 180s = 3 phút). |
| `ocr.room_id_region` | **Tọa độ khung chữ chứa ID Phòng** trên màn hình của Master (X, Y, W-chiều rộng, H-chiều cao). *Cần chụp màn hình và đo khoảng này cho chính xác để OCR có thể đọc chuẩn số ID phòng.* |
| `timeouts` | Thời gian chờ tối đa (giây) cho mỗi bước. Nếu máy tính load game chậm, bạn có thể tăng các con số này. |

---

## 5. Hướng dẫn chạy Tool

1. Mở phần mềm **LDMultiPlayer**.
2. Khởi động tất cả các giả lập mà bạn đã điền trong phần `instance_groups` (cả Master và Slave).
3. Mở game Liên Quân Mobile trên tất cả các giả lập và đăng nhập sẵn vào màn hình chính. *Lưu ý: Tắt thủ công các popup quảng cáo lớn nếu được để tool chạy mượt hơn từ đầu.*
4. Mở Command Prompt (cmd) / PowerShell tại thư mục `AOV_tools`.
5. Chạy lệnh kích hoạt tool:
   ```bash
   python main.py
   ```
6. Tool sẽ bắt đầu tự động hóa, bạn có thể theo dõi quá trình chạy thông qua màn hình Console. Các lỗi hoặc chi tiết chạy cũng được lưu lại vào thư mục `logs/`. 
7. **Trong lúc tool chạy, hạn chế click chuột vào màn hình giả lập để tránh làm lệch thao tác của giả lập.**

### Luồng hoạt động tự động của Tool:
- **Phase 1**: Lần lượt trên các giả lập: Nhận thưởng > Vào Cửa hàng mua vật phẩm > Mở túi đồ sử dụng vật phẩm.
- **Phase 2**: Các Master sẽ tạo phòng và dùng thuật toán OCR quét màn hình để lấy số ID phòng. Các Slaves sau đó sẽ tự động gõ ID này để vào chung phòng với Master.
- **Phase 3**: Tự động chọn tướng và khóa. Khi trận đấu bắt đầu load xong (battlefield), Master sẽ bấm đồng hồ đếm. Đúng `180` giây sau, Master ra lệnh để tất cả cùng bật/tắt 1 tính năng. Sau khi trận kết thúc, tool tự bấm bỏ qua kết quả và ấn **Chơi lại** để tiếp tục lặp lại Phase 3 cho đến khi đủ số `match_count`. Trận cuối cùng tool sẽ ấn thoát phòng.
