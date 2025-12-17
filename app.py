import os
import queue
import shutil
import subprocess
import tempfile
import threading
from datetime import datetime
from pathlib import Path

import streamlit as st

# --- CẤU HÌNH TRANG & CSS ---
st.set_page_config(
    page_title="Video Processor Pro", layout="wide", initial_sidebar_state="expanded"
)


# --- LOAD CSS ---
def load_css(file_name):
    with open(file_name) as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)


load_css("assets/style.css")

# --- KHỞI TẠO GLOBAL QUEUE & STATE ---
# Queue dùng để gửi kết quả từ Thread xử lý về Main Thread
if "result_queue" not in st.session_state:
    st.session_state["result_queue"] = queue.Queue()

if "stop_event" not in st.session_state:
    st.session_state["stop_event"] = threading.Event()

if "processing_thread" not in st.session_state:
    st.session_state["processing_thread"] = None


# --- CORE FUNCTIONS (CHẠY TRONG THREAD) ---
def process_video_task(
    input_path, output_path, platform, speed, options, queue_obj, stop_event
):
    """Hàm xử lý chạy trong thread riêng với các hiệu ứng nâng cao"""

    if stop_event.is_set():
        return

    # --- 1. XÂY DỰNG VIDEO FILTERS ---
    filters = []

    # a. Speed (Video)
    # setpts=PTS/speed
    filters.append(f"setpts=PTS/{speed}")

    # b. Platform Colors & Flip (Cơ bản)
    if platform == "TikTok":
        # Saturation 1.2, Contrast 1.05, Flip
        filters.append("eq=saturation=1.2:contrast=1.05")
        filters.append("hflip")
    else:
        # Brightness 0.05, Contrast 1.1, Flip
        filters.append("eq=brightness=0.05:contrast=1.1")
        filters.append("hflip")

    # c. Advanced Visual Options
    # Rotation (Mới) - Đặt trước Crop để tránh bị đen góc nếu combine
    rotate_angle = options.get("rotate", 0)
    if rotate_angle != 0:
        # Xoay và lấp đầy nền đen (tuy nhiên nếu có crop sau đó thì sẽ cắt hết đen)
        # Sử dụng ow, oh mặc định sẽ giữ nguyên kích thước khung hình nhưng bị đen góc
        # PI = 3.141592653589793
        filters.append(f"rotate={rotate_angle}*PI/180")
    if options.get("zoom_crop"):
        # Zoom & Crop 10%: crop=iw*0.9:ih*0.9 -> scale=iw:ih
        filters.append("crop=iw*0.9:ih*0.9")
        filters.append("scale=iw:ih")

    if options.get("add_noise"):
        # Thêm nhiễu hạt nhẹ: alls=10 (cường độ), allf=t (temporal noise)
        filters.append("noise=alls=10:allf=t+u")

    if options.get("vignette"):
        # Hiệu ứng tối 4 góc
        filters.append("vignette")

    # Gộp các filter hình ảnh thành chuỗi
    vf_string = ",".join(filters)

    # --- 2. XÂY DỰNG AUDIO FILTERS ---
    # Mục tiêu: Đạt được Video Speed yêu cầu, đồng thời apply các hiệu ứng âm thanh
    audio_chains = []

    if not options.get("mute_audio"):
        # Logic tính toán Speed & Pitch
        # Video đang chạy ở tốc độ = 'speed' (ví dụ 1.05)
        # Audio phải khớp tốc độ này.

        current_audio_speed = 1.0

        # a. Pitch Shifting (Làm méo giọng)
        if options.get("pitch_shift"):
            # Tăng pitch lên 5% bằng cách tăng sample rate
            # Điều này làm audio nhanh hơn 1.05 lần
            pitch_factor = 1.05
            audio_chains.append(f"asetrate=44100*{pitch_factor},aresample=44100")
            current_audio_speed *= pitch_factor

        # b. Equalizer (Cắt Bass - Low Cut)
        if options.get("low_bass"):
            # Giảm 10dB ở tần số 100Hz (Width type h = Hz)
            audio_chains.append("equalizer=f=100:width_type=h:width=200:g=-10")

        # c. Final Speed Adjustment (Atempo)
        # Ta cần đưa tốc độ audio về đúng bằng 'speed' của video
        # Hệ số cần điều chỉnh = speed_mong_muốn / speed_hiện_tại
        needed_tempo = speed / current_audio_speed

        # Atempo giới hạn từ 0.5 đến 2.0. Nếu vượt quá phải chain nhiều cái (nhưng ở đây diff nhỏ nên chắc không sao)
        audio_chains.append(f"atempo={needed_tempo}")

    # --- 3. LỆNH FFMPEG ---
    command = ["ffmpeg", "-i", str(input_path)]

    # Apply Video Filters
    command.extend(["-vf", vf_string])

    # Apply Audio Filters
    if options.get("mute_audio"):
        command.append("-an")  # No Audio
    else:
        af_string = ",".join(audio_chains)
        if af_string:
            command.extend(["-af", af_string])
        command.extend(["-c:a", "aac"])

    # Output Settings
    command.extend(["-y", "-c:v", "libx264", str(output_path)])

    # --- 4. EXECUTE ---
    try:
        # Chạy FFmpeg - map_metadata -1 để xóa thông tin gốc
        full_cmd = command[:3] + ["-map_metadata", "-1"] + command[3:]

        result = subprocess.run(full_cmd, capture_output=True, text=True)
        is_success = result.returncode == 0
        error_msg = result.stderr if not is_success else None
    except Exception as e:
        is_success = False
        error_msg = str(e)

    # 5. Generate Thumbnail nếu thành công

    # 6. Send Result
    if not stop_event.is_set():
        result_data = {
            "type": "video_done" if is_success else "video_error",
            "filename": input_path.name,
            "output_name": output_path.name,
            "output_path": str(output_path),
            "thumb_path": None,
            "size": f"{os.path.getsize(output_path) / (1024 * 1024):.1f} MB"
            if is_success
            else "0 MB",
            "error": error_msg,
        }
        queue_obj.put(result_data)


def worker_main(
    file_paths,
    output_dir,
    platform,
    speed,
    options,
    result_queue,
    stop_event,
):
    """Hàm main của Worker Thread - Lặp qua list file"""
    total = len(file_paths)
    result_queue.put({"type": "start", "total": total})

    for i, input_path in enumerate(file_paths):
        if stop_event.is_set():
            break

        # Báo đang xử lý file nào
        result_queue.put(
            {"type": "processing", "index": i, "filename": input_path.name}
        )

        filename = input_path.name
        prefix = "tiktok" if platform == "TikTok" else "shorts"
        output_filename = f"{prefix}_{filename}"
        output_path = output_dir / output_filename
        output_path = output_dir / output_filename

        process_video_task(
            input_path,
            output_path,
            platform,
            speed,
            options,
            result_queue,
            stop_event,
        )

    result_queue.put({"type": "complete"})


def create_zip_archive(source_dir, output_filename):
    return shutil.make_archive(output_filename.replace(".zip", ""), "zip", source_dir)


# --- POPUP VIEW ---
@st.dialog("🎥 Xem trước Video", width="large")
def preview_modal(video_path, video_name):
    st.subheader(video_name)
    st.video(video_path)


# --- RENDER HELPER (FRAGMENT) ---
@st.fragment(run_every=1)
def display_results_fragment():
    """
    Fragment xử lý hiển thị kết quả và cập nhật tiến độ Real-time.
    """
    is_running = st.session_state.get("is_running", False)

    # 1. POLL QUEUE (Cập nhật trạng thái)
    # Lấy tin nhắn từ worker thread để update session_state
    if is_running:
        try:
            for _ in range(10):  # Batch process messages
                msg = st.session_state["result_queue"].get_nowait()

                if msg["type"] == "start":
                    st.session_state["progress_info"]["total"] = msg["total"]

                elif msg["type"] == "processing":
                    st.session_state["progress_info"]["current"] = msg["index"]
                    st.session_state["progress_info"]["status"] = msg["filename"]

                elif msg["type"] == "video_done":
                    st.session_state["processed_results"].append(
                        {
                            "name": msg["output_name"],
                            "path": msg["output_path"],
                            "thumb": msg["thumb_path"],
                            "size": msg["size"],
                        }
                    )
                    st.session_state["progress_info"]["current"] += 1

                elif msg["type"] == "video_error":
                    st.error(f"Lỗi xử lý {msg['filename']}: {msg['error']}")
                    st.session_state["progress_info"]["current"] += 1

                elif msg["type"] == "complete":
                    st.session_state["is_running"] = False
                    st.toast("🎉 Đã xử lý xong toàn bộ video!", icon="✅")

                    # Auto scroll to results
                    st.markdown(
                        """
                        <script>
                            var element = window.parent.document.getElementById("results_section");
                            if (element) {
                                element.scrollIntoView({behavior: "smooth", block: "start"});
                            }
                        </script>
                        """,
                        unsafe_allow_html=True,
                    )
                    # KHÔNG gọi st.rerun() ở đây để tránh tắt popup
        except queue.Empty:
            pass

    # 2. HIỂN THỊ TIẾN ĐỘ (Ngay trong fragment để update mỗi 1s)
    prog = st.session_state.get("progress_info", {})
    total = prog.get("total", 0)
    current = prog.get("current", 0)

    if total > 0:
        # Tính %
        ratio = current / total
        st.progress(min(ratio, 1.0))

        if is_running:
            st.caption(
                f"⏳ Đang xử lý: **{prog.get('status', '...')}** ({current}/{total})"
            )
        else:
            st.caption(f"✅ Hoàn tất ({total}/{total})")

    # 3. HIỂN THỊ DANH SÁCH KẾT QUẢ
    results = st.session_state["processed_results"]
    if not results:
        if is_running:
            st.info("⏳ Đang khởi động máy làm video...")
        return

    # ZIP Download
    first_path = Path(results[0]["path"])
    zip_base = first_path.parent.parent / "all_videos"
    if not os.path.exists(f"{zip_base}.zip"):
        create_zip_archive(first_path.parent, str(zip_base))

    zip_name = f"{datetime.now().strftime('%y%m%d_%H%M%S')}_{len(results)}_videos.zip"
    with open(f"{zip_base}.zip", "rb") as f_zip:
        st.download_button(
            label=f"📦 Tải tất cả ({len(results)} videos)",
            data=f_zip.read(),
            file_name=zip_name,
            mime="application/zip",
            type="primary",
            key=f"dl_all_{len(results)}",
        )

    # Grid Render
    # Grid Render
    # Mobile: cols=2 (Streamlit auto stacks), Desktop: cols=3 or 5 để khung video đủ lớn
    cols_per_row = 5
    rows = [results[i : i + cols_per_row] for i in range(0, len(results), cols_per_row)]

    for row_idx, row in enumerate(rows):
        cols = st.columns(cols_per_row)
        for idx, item in enumerate(row):
            with cols[idx]:
                with st.container(border=True):
                    # Video Player
                    st.video(item["path"])

                    # Info
                    name = item["name"]
                    short_name = (name[:40] + "...") if len(name) > 40 else name
                    st.markdown(f"**{short_name}**", help=name)
                    st.caption(item["size"])

                    # Download Button only
                    suffix = f"{row_idx}_{idx}"
                    with open(item["path"], "rb") as f:
                        st.download_button(
                            "⬇️ Tải xuống",
                            f,
                            file_name=name,
                            key=f"d_{suffix}_{name}",
                            use_container_width=True,
                        )


# --- MAIN APP ---
def main():
    if "processed_results" not in st.session_state:
        st.session_state["processed_results"] = []
    if "temp_obj" not in st.session_state:
        st.session_state["temp_obj"] = None
    if "is_running" not in st.session_state:
        st.session_state["is_running"] = False
    if "progress_info" not in st.session_state:
        st.session_state["progress_info"] = {"current": 0, "total": 0, "status": ""}

    st.title("🎬 Video Tool Pro")

    # --- 1. SIDEBAR: CẤU HÌNH (SETTINGS) ---
    with st.sidebar:
        st.header("⚙️ Cấu hình")
        is_disabled = st.session_state["is_running"]

        # A. Platform & Speed
        st.subheader("1. Cơ bản")
        platform = st.radio(
            "Nền tảng mục tiêu (Platform)",
            ["TikTok", "YouTube Shorts"],
            disabled=is_disabled,
            help="Chọn nền tảng để áp dụng bộ lọc màu và kích thước video phù hợp.",
        )

        st.caption(
            """
            ℹ️ **Khác biệt xử lý:**
            - **TikTok**: Lật gương (Flip), tăng độ bão hòa (Saturation), làm màu video rực rỡ hơn.
            - **YouTube**: Lật gương (Flip), tăng độ sáng (Brightness), làm video sáng rõ hơn.
            """
        )

        default_speed = 1.05 if platform == "TikTok" else 1.02
        speed = st.slider(
            "Tốc độ phát (Speed Control)",
            0.5,
            2.0,
            default_speed,
            0.05,
            disabled=is_disabled,
            help="Tăng/Giảm tốc độ video. Mặc định: TikTok 1.05x, YouTube 1.02x để tránh trùng lặp nội dung.",
        )

        # B. Visual Options
        st.subheader("2. Hình ảnh (Visual)")
        opt_zoom = st.checkbox(
            "Zoom 10% & Crop",
            value=True,
            disabled=is_disabled,
            help="Phóng to video 10% rồi cắt viền xung quanh. Giúp loại bỏ watermark ở cạnh và thay đổi cấu trúc khung hình (Anti-frame check).",
        )
        opt_noise = st.checkbox(
            "Làm nhiễu (Add Noise)",
            value=False,
            disabled=is_disabled,
            help="Phủ một lớp nhiễu mỏng lên video. Giúp thay đổi mã hóa từng pixel, chống quét trùng lặp mã Hash (Digital Fingerprint).",
        )
        opt_vignette = st.checkbox(
            "Vignette (Tối 4 góc)",
            value=False,
            disabled=is_disabled,
            help="Làm tối dần 4 góc video. Thay đổi biểu đồ ánh sáng (Histogram) của video để khác biệt so với gốc.",
        )

        opt_rotate = st.slider(
            "Xoay nghiêng (Độ)",
            -5,
            5,
            0,
            1,
            disabled=is_disabled,
            help="Xoay video một góc nhỏ (-5 đến 5 độ). Rất hiệu quả để tránh khớp khung hình (Visual Match). Nên dùng kèm Zoom & Crop để tránh viền đen.",
        )

        # C. Audio Options
        st.subheader("3. Âm thanh (Audio)")
        opt_pitch = st.checkbox(
            "Đổi giọng (Pitch Shifting)",
            value=True,
            disabled=is_disabled,
            help="Tăng cao độ âm thanh (Pitch) lên 5%. Giúp giọng nói/âm nhạc khác đi so với bản gốc để tránh quét bản quyền âm thanh (Audio Match).",
        )
        opt_bass = st.checkbox(
            "Giảm Bass (Low Cut)",
            value=False,
            disabled=is_disabled,
            help="Cắt bớt tần số âm trầm (Bass) dưới 100Hz. Làm thay đổi phổ âm thanh.",
        )
        opt_mute = st.checkbox(
            "Tắt tiếng (Mute Audio)",
            value=False,
            disabled=is_disabled,
            help="Loại bỏ hoàn toàn âm thanh. An toàn tuyệt đối về bản quyền âm nhạc.",
        )

    # --- 2. MAIN CONTENT: UPLOAD & ACTION ---

    # Khu vực Upload: Gom vào Expander để tiết kiệm diện tích
    with st.expander("📂 Kéo thả hoặc Chọn Video để xử lý", expanded=True):
        uploaded_files = st.file_uploader(
            "Upload Video (.mp4, .mov)",
            type=["mp4", "mov"],
            accept_multiple_files=True,
            disabled=is_disabled,
            label_visibility="collapsed",
        )
        if not uploaded_files:
            st.caption(
                "👆 Hỗ trợ định dạng .mp4, .mov. Có thể chọn nhiều file cùng lúc."
            )
        else:
            st.caption(f"✅ Đã chọn **{len(uploaded_files)}** video.")

    # Action Buttons
    if not st.session_state["is_running"]:
        if st.button(
            "🚀 CHẠY",
            type="primary",
            use_container_width=True,
            disabled=not uploaded_files,
        ):
            # START LOGIC
            if st.session_state["temp_obj"]:
                try:
                    st.session_state["temp_obj"].cleanup()
                except Exception:
                    pass

            # Gom options
            options = {
                "zoom_crop": opt_zoom,
                "add_noise": opt_noise,
                "vignette": opt_vignette,
                "mute_audio": opt_mute,
                "pitch_shift": opt_pitch,
                "low_bass": opt_bass,
                "rotate": opt_rotate,
            }

            st.session_state["processed_results"] = []
            st.session_state["is_running"] = True
            st.session_state["stop_event"].clear()
            st.session_state["progress_info"] = {
                "current": 0,
                "total": 0,
                "status": "Starting...",
            }

            # Setup Temp
            temp_obj = tempfile.TemporaryDirectory()
            st.session_state["temp_obj"] = temp_obj
            temp_path = Path(temp_obj.name)
            (temp_path / "input").mkdir()
            (temp_path / "output").mkdir()

            # Save Inputs
            file_paths = []
            for uf in uploaded_files:
                p = temp_path / "input" / uf.name
                with open(p, "wb") as f:
                    f.write(uf.getbuffer())
                file_paths.append(p)

            # Start Thread
            t = threading.Thread(
                target=worker_main,
                args=(
                    file_paths,
                    temp_path / "output",
                    platform,
                    speed,
                    options,
                    st.session_state["result_queue"],
                    st.session_state["stop_event"],
                ),
            )
            t.start()
            st.session_state["processing_thread"] = t
            st.rerun()
    else:
        if st.button("⏹️ DỪNG", type="secondary", use_container_width=True):
            st.session_state["stop_event"].set()
            st.session_state["is_running"] = False
            st.rerun()
    # Results Layout
    # Create a column for results to place the anchor
    col_result = st.container()
    with col_result:
        # Anchor for scrolling
        st.markdown('<div id="results_section"></div>', unsafe_allow_html=True)
        if st.session_state["processed_results"] or st.session_state["is_running"]:
            display_results_fragment()
            # Inject JavaScript to scroll to the results section when processing is complete
            if (
                st.session_state["processed_results"]
                and not st.session_state["is_running"]
            ):
                st.markdown(
                    """
                    <script>
                        var element = document.getElementById('results_section');
                        if (element) {
                            element.scrollIntoView({behavior: 'smooth'});
                        }
                    </script>
                    """,
                    unsafe_allow_html=True,
                )


if __name__ == "__main__":
    main()
