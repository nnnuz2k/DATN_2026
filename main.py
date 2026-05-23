import cv2
import sys
import os
import time
import numpy as np
from ultralytics import YOLO
from pygame import mixer
import tkinter as tk
from tkinter import messagebox, ttk
import threading
from PIL import Image, ImageTk, ImageDraw, ImageFont

# --- 1. HÀM LẤY ĐƯỜNG DẪN TƯƠNG THÍCH HỆ THỐNG ---
def get_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

# --- 2. KHỞI TẠO AI TĂNG TỐC PHẦN CỨNG (GPU CUDA) & ÂM THANH ---
path_model = get_path("best.pt")
model = YOLO(path_model)

try:
    import torch
    if torch.cuda.is_available():
        model.to('cuda')
        print("\n" + "="*60)
        print(f"🚀 [THÀNH CÔNG]: ĐÃ KÍCH HOẠT TĂNG TỐC PHẦN CỨNG GPU!")
        print(f"🔥 ĐANG CHẠY AI TRÊN: {torch.cuda.get_device_name(0)}")
        print("="*60 + "\n")
    else:
        print("\n" + "="*60)
        print("⚠️ [CẢNH BÁO]: Thư viện CUDA chưa sẵn sàng, AI chạy bằng CPU.")
        print("="*60 + "\n")
except Exception as e:
    print(f"❌ Lỗi cấu hình tăng tốc phần cứng: {e}")

mixer.init()
path_audio = get_path("coibaochay.mp3")
alert_sound = mixer.Sound(path_audio) if os.path.exists(path_audio) else None

# --- 3. BIẾN TOÀN CỤC QUẢN LÝ TẬP TRUNG ---
last_drowning_time = 0
drowning_timeout = 5
drowning_status_dict = {}  
camera_frames = {}          
active_caps = {}           
camera_counter = 0         
is_running = True          
status_text_global = "Trạng thái: Ổn định"  
drowning_start_time = 0  
monitor_list = None  

# --- Hàm đóng cửa sổ hệ thống ---
def on_closing():
    global is_running
    if messagebox.askokcancel("Thoát", "Xác nhận đóng toàn bộ hệ thống giám sát trung tâm?"):
        is_running = False
        time.sleep(0.3)
        for cap in active_caps.values(): cap.release()
        mixer.quit()
        root.destroy()
        sys.exit()

# --- HÀM LÀM SẠCH / RESET HỆ THỐNG THUẦN VIỆT ---
def reset_system():
    global camera_counter, last_drowning_time, drowning_start_time, status_text_global
    
    for cap in list(active_caps.values()):
        try: cap.release()
        except: pass
        
    active_caps.clear()
    camera_frames.clear()
    drowning_status_dict.clear()
    
    camera_counter = 0
    last_drowning_time = 0
    drowning_start_time = 0
    status_text_global = "Trạng thái: Ổn định"
    
    try:
        if mixer.get_init() and mixer.get_busy():
            mixer.stop()
    except:
        pass
        
    if monitor_list:
        monitor_list.delete(0, tk.END)
        monitor_list.insert(tk.END, "🔄 Đã làm mới toàn bộ hệ thống!")
        
    print("🔄 [RESET]: Đã giải phóng toàn bộ Camera và đưa hệ thống về trạng thái sẵn sàng.")

# --- 4. LUỒNG ĐỌC CAMERA VÀ SỬ DỤNG AI ĐA LUỒNG TỐI ƯU ---
def process_camera(cam_id, url, listbox_widget):
    global last_drowning_time
    cap = cv2.VideoCapture(url)
    
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    
    active_caps[cam_id] = cap
    frame_count = 0
    AI_CHECK_INTERVAL = 3  
    saved_boxes = []
    is_drowning = False
    
    while is_running and cam_id in active_caps and cap.isOpened():
        success, frame = cap.read()
        
        if not success or frame is None or frame.size == 0:
            if isinstance(url, str) and not url.startswith("http"):
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue
            time.sleep(0.02)
            continue

        frame_count += 1

        if isinstance(url, str) and "http" in url.lower():
            frame = cv2.flip(frame, 1) 

        if frame_count % AI_CHECK_INTERVAL == 0:
            results = model(frame, conf=0.50, verbose=False)
            is_drowning = False
            saved_boxes = []

            for r in results:
                for box in r.boxes:
                    cls = int(box.cls[0])
                    label_name = model.names[cls]  

                    # Việt hóa nhãn hiển thị trực tiếp đè lên khung hình bounding box
                    if label_name == 'drowning':
                        is_drowning = True
                        x1, y1, x2, y2 = map(int, box.xyxy[0])
                        saved_boxes.append((x1, y1, x2, y2, "NGUY HIỂM DUỐI NƯỚC!", (0, 0, 255)))  
                        
                    elif label_name == 'swimming':
                        x1, y1, x2, y2 = map(int, box.xyxy[0])
                        saved_boxes.append((x1, y1, x2, y2, "An toàn (Đang bơi)", (0, 255, 0)))  
                        
        current_time = time.time()
        if is_drowning:
            last_drowning_time = current_time
            drowning_status_dict[cam_id] = True
        else:
            drowning_status_dict[cam_id] = False

        for (x1, y1, x2, y2, text, color) in saved_boxes:
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.putText(frame, text, (x1, y1 - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

        camera_frames[cam_id] = frame
        time.sleep(0.005)

    cap.release()
    if cam_id in active_caps: del active_caps[cam_id]
    if cam_id in camera_frames: del camera_frames[cam_id]
    drowning_status_dict[cam_id] = False

# --- 5. LUỒNG KIỂM SOÁT CÒI BÁO ĐỘNG THÔNG MINH ---
def alarm_control_loop():
    global last_drowning_time, drowning_start_time, status_text_global
    
    REQUIRED_DROWNING_DURATION = 3.0  
    COOLDOWN_HOLD_TIME = 2.0          
    
    while is_running:
        current_time = time.time()
        any_drowning = any(drowning_status_dict.values()) if drowning_status_dict else False

        if any_drowning:
            if drowning_start_time == 0:
                drowning_start_time = current_time
            
            total_duration = current_time - drowning_start_time
            status_text_global = f"⚠️ Phát hiện nguy hiểm!\nĐang xác thực: {total_duration:.1f}giây / {REQUIRED_DROWNING_DURATION}giây"
            
            if total_duration >= REQUIRED_DROWNING_DURATION:
                status_text_global = "🚨 BÁO ĐỘNG: CÓ ĐUỐI NƯỚC!"
                if alert_sound and not mixer.get_busy():
                    alert_sound.play(-1)
        else:
            if last_drowning_time != 0 and (current_time - last_drowning_time > COOLDOWN_HOLD_TIME):
                drowning_start_time = 0
                status_text_global = "Trạng thái: Ổn định"
                
                if current_time - last_drowning_time > drowning_timeout:
                    if mixer.get_busy():
                        mixer.stop()
                        last_drowning_time = 0
            elif drowning_start_time != 0:
                status_text_global = f"⚠️ Nghi vấn gián đoạn...\nĐang giữ bộ nhớ còi."
                        
        time.sleep(0.1)

# --- 6. GIAO DIỆN HỢP NHẤT TRUNG TÂM (THUẦN VIỆT DASHBOARD) ---
def build_integrated_dashboard():
    global camera_counter, is_running, root, monitor_list
    
    root = tk.Tk()
    root.title("HỆ THỐNG GIÁM SÁT HỒ BƠI TÍCH HỢP AI TRUNG TÂM")
    root.configure(bg="#1A1A1A")
    root.attributes("-fullscreen", True) 
    
    def quick_quit(event=None):
        on_closing()
        
    root.bind("<Escape>", quick_quit) 
    
    video_background = tk.Label(root, bg="#121212")
    video_background.pack(fill="both", expand=True)

    # Tăng nhẹ chiều cao panel trái để chữ tiếng Việt không bị co ghim
    left_panel = tk.Frame(root, width=290, height=580, bg="#252526", padx=10, pady=10, highlightbackground="#00FF7F", highlightthickness=1)
    left_panel.place(x=20, y=20) 
    left_panel.pack_propagate(False) 
    
    # Việt hóa tiêu đề panel điều khiển trung tâm
    tk.Label(left_panel, text="TRUNG TÂM GIÁM SÁT BỂ BƠI", font=("Arial", 11, "bold"), bg="#252526", fg="#00FF7F").pack(pady=3)
    
    status_label = tk.Label(left_panel, text="Trạng thái: Ổn định", font=("Arial", 9, "bold"), bg="#1E1E1E", fg="#FFFFFF", pady=5, justify="center")
    status_label.pack(fill="x", pady=5)
    
    ip_frame = tk.LabelFrame(left_panel, text=" Kết nối Nguồn vào (Camera IP / Video) ", font=("Arial", 8), bg="#252526", fg="#FFFFFF", padx=5, pady=3)
    ip_frame.pack(fill="x", pady=5)
    
    DEFAULT_IP = "192.168.1.5:8080"
    
    ip_entry = tk.Entry(ip_frame, font=("Arial", 9), bg="#333333", fg="#FFFFFF", insertbackground="white")
    ip_entry.insert(0, DEFAULT_IP)
    ip_entry.pack(fill="x", pady=3)
    
    def add_camera_btn_click():
        global camera_counter
        raw_ip = ip_entry.get().strip()
        if not raw_ip:
            messagebox.showwarning("Nhắc nhở", "Vui lòng nhập địa chỉ IP hoặc tên file Video!")
            return
        
        camera_counter += 1
        
        if raw_ip.lower().endswith(('.mp4', '.avi', '.mkv', '.mov')):
            stream_url = get_path(raw_ip)  
            monitor_list.insert(tk.END, f"🎬 Mở Video mẫu: {raw_ip}")
        else:
            stream_url = f"http://{raw_ip}/video"  
            monitor_list.insert(tk.END, f"▶️ Mở luồng Kênh Camera IP {camera_counter}")
        
        cam_thread = threading.Thread(target=process_camera, args=(camera_counter, stream_url, monitor_list), daemon=True)
        cam_thread.start()
        
        monitor_list.see(tk.END)
        
        ip_entry.delete(0, tk.END)
        ip_entry.insert(0, DEFAULT_IP)
        
    tk.Button(ip_frame, text="⚡ KẾT NỐI HỆ THỐNG", command=add_camera_btn_click, bg="#0078D7", fg="white", font=("Arial", 8, "bold"), pady=2).pack(fill="x", pady=3)
    
    control_btn_frame = tk.Frame(ip_frame, bg="#252526")
    control_btn_frame.pack(fill="x", pady=3)
    
    # Việt hóa nút Reset thành LÀM MỚI
    tk.Button(control_btn_frame, text="🔄 LÀM MỚI", command=reset_system, bg="#D83B01", fg="white", font=("Arial", 8, "bold"), pady=2).pack(side="left", fill="x", expand=True, padx=(0, 2))
    
    # Việt hóa nút Thoát
    tk.Button(control_btn_frame, text="❌ THOÁT APP", command=on_closing, bg="#A80000", fg="white", font=("Arial", 8, "bold"), pady=2).pack(side="right", fill="x", expand=True, padx=(2, 0))
    
    log_frame = tk.LabelFrame(left_panel, text=" Nhật ký hệ thống trung tâm ", font=("Arial", 8), bg="#252526", fg="#FFFFFF", padx=5, pady=3)
    log_frame.pack(fill="both", expand=True, pady=3)
    monitor_list = tk.Listbox(log_frame, font=("Courier New", 8), bg="#1E1E1E", fg="#00FF00", borderwidth=0, highlightthickness=0)
    monitor_list.pack(fill="both", expand=True)

    try:
        viet_font_large = ImageFont.truetype("arial.ttf", 25)
        viet_font_small = ImageFont.truetype("arial.ttf", 16)
    except:
        viet_font_large = ImageFont.load_default()
        viet_font_small = ImageFont.load_default()

    def update_video_stream():
        if not is_running: return
        
        status_label.config(text=status_text_global)
        if "BÁO ĐỘNG" in status_text_global:
            status_label.config(fg="#FF0000", bg="#5A0000")
        elif "⚠️" in status_text_global:
            status_label.config(fg="#FFCC00", bg="#3A3A00")
        else:
            status_label.config(fg="#00FF7F", bg="#1E1E1E")
            
        frames_list = list(camera_frames.values())
        num_cams = len(frames_list)
        
        current_w = video_background.winfo_width()
        current_h = video_background.winfo_height()
        
        if current_w < 10 or current_h < 10:
            root.after(100, update_video_stream)
            return

        if num_cams == 0:
            grid_frame = np.zeros((current_h, current_w, 3), dtype=np.uint8)
            pil_img_font = Image.fromarray(grid_frame)
            draw = ImageDraw.Draw(pil_img_font)
            # Việt hóa màn hình chờ luồng nhận diện
            draw.text((current_w // 2 - 320, current_h // 2 - 25), "HỆ THỐNG SẴN SÀNG: VUI LÒNG KẾT NỐI CAMERA HOẶC VIDEO", font=viet_font_large, fill=(0, 255, 0))
            grid_frame = np.array(pil_img_font)
        else:
            if num_cams == 1:
                grid_frame = cv2.resize(frames_list[0], (current_w, current_h))
            elif num_cams == 2:
                half_w = current_w // 2
                f1 = cv2.resize(frames_list[0], (half_w, current_h))
                f2 = cv2.resize(frames_list[1], (half_w, current_h))
                grid_frame = np.hstack((f1, f2))
            else:
                half_w = current_w // 2
                half_h = current_h // 2
                while len(frames_list) < 4:
                    black_filler = np.zeros((half_h, half_w, 3), dtype=np.uint8)
                    pil_filler = Image.fromarray(black_filler)
                    draw_filler = ImageDraw.Draw(pil_filler)
                    draw_filler.text((half_w // 2 - 80, half_h // 2 - 10), "Đang chờ kết nối tiếp...", font=viet_font_small, fill=(120, 120, 120))
                    frames_list.append(np.array(pil_filler))
                
                f1 = cv2.resize(frames_list[0], (half_w, half_h))
                f2 = cv2.resize(frames_list[1], (half_w, half_h))
                f3 = cv2.resize(frames_list[2], (half_w, half_h))
                f4 = cv2.resize(frames_list[3], (half_w, half_h))
                
                top_row = np.hstack((f1, f2))
                bottom_row = np.hstack((f3, f4))
                grid_frame = np.vstack((top_row, bottom_row))

        cv2_rgb = cv2.cvtColor(grid_frame, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(cv2_rgb)
        img_tk = ImageTk.PhotoImage(image=pil_img)
        
        video_background.img_tk = img_tk
        video_background.config(image=img_tk)
        
        video_background.after(60, update_video_stream)

    threading.Thread(target=alarm_control_loop, daemon=True).start()
    root.after(200, update_video_stream)

    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()

if __name__ == "__main__":
    build_integrated_dashboard()