import os
import time
from tkinter import ttk  # 用于创建进度条
import threading  # 用于多线程下载
import webbrowser  # 用于打开超链接
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from urllib.parse import urljoin, urlparse
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor
import tkinter as tk
from tkinter import messagebox



def safe_download(url, save_path, max_retry=5):
    """安全下载文件，带重试机制和进度条"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Referer': 'https://www.girl-atlas.com/'
    }

    for _ in range(max_retry):
        try:
            response = requests.get(url, headers=headers, stream=True, timeout=60)
            if response.status_code == 200:
                total_size = int(response.headers.get('content-length', 0))
                with open(save_path, 'wb') as f:
                    with tqdm(
                            total=total_size,
                            unit='B',
                            unit_scale=True,
                            desc=os.path.basename(save_path),
                            ncols=80
                    ) as pbar:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                                pbar.update(len(chunk))
                return True
        except Exception as e:
            print(f"下载失败，重试中... ({str(e)})")
            time.sleep(2)
    return False


def get_dynamic_content(url):
    """使用Selenium获取动态渲染后的页面内容，并模拟点击缩略图以加载高清图片"""
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")

    driver = webdriver.Chrome(options=chrome_options)
    driver.get(url)

    # 等待页面加载完成
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "img[data-src$='!sml']"))
    )

    # 滚动页面，直到不再加载新的图片
    last_height = driver.execute_script("return document.body.scrollHeight")
    while True:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)  # 等待新内容加载

        # 获取新滚动后页面的高度
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:  # 如果高度没变，说明已经没有新内容加载
            break
        last_height = new_height

    # 显式等待所有缩略图加载
    WebDriverWait(driver, 5).until(
        EC.presence_of_all_elements_located((By.CSS_SELECTOR, "img[data-src$='!sml']"))
    )

    # 获取缩略图元素
    thumbnails = driver.find_elements(By.CSS_SELECTOR, "img[data-src$='!sml']")

    # 存储所有下载的 !lrg 图片 URL
    lrg_urls = set()

    # 点击缩略图，确保所有高清图片加载
    for thumbnail in thumbnails:
        try:
            # 点击缩略图
            thumbnail.click()
            time.sleep(0.5)  # 等待高清图片加载

            # 获取当前页面所有 !lrg 图片 URL
            new_lrg_images = driver.find_elements(By.CSS_SELECTOR, "img[src$='!lrg']")
            for img in new_lrg_images:
                img_url = img.get_attribute("src")
                if img_url and '!lrg' in img_url:
                    lrg_urls.add(img_url)

            # 关闭预览框
            close_button = WebDriverWait(driver, 3).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, ".f-button[data-fancybox-close]"))
            )
            close_button.click()
            time.sleep(0.3)  # 适当缩短等待时间
        except Exception as e:
            print(f"处理缩略图时出错: {str(e)}")

    # 确保所有图片都已加载
    assert len(lrg_urls) == len(thumbnails), "图片数量不一致，可能未完全加载"

    driver.quit()
    return lrg_urls



def download_image(img_url, save_path):
    """下载单张图片并重命名"""
    if safe_download(img_url, save_path):
        # 重命名文件，移除 !lrg 后缀
        new_filename = save_path.replace('.jpg!lrg', '.jpg')
        os.rename(save_path, new_filename)
        print(f"已重命名: {os.path.basename(save_path)} -> {os.path.basename(new_filename)}")


def parse_album(url):
    # 创建下载目录
    domain = urlparse(url).netloc
    save_dir = os.path.join("downloads", domain)
    os.makedirs(save_dir, exist_ok=True)

    # 获取高清图片 URL（!lrg）
    lrg_urls = get_dynamic_content(url)

    # 解析相册标题
    html = requests.get(url).text
    soup = BeautifulSoup(html, 'html.parser')
    title = soup.find('h1').text.strip() if soup.find('h1') else "untitled"
    album_dir = os.path.join(save_dir, title)
    os.makedirs(album_dir, exist_ok=True)

    # 多线程下载高清图片（!lrg）并重命名
    with ThreadPoolExecutor(max_workers=10) as executor:  # 使用线程池并行下载
        futures = []
        for idx, img_url in enumerate(lrg_urls, 1):
            # 确保 URL 包含 !lrg 后缀
            if '!lrg' not in img_url:
                continue

            # 拼接完整 URL
            img_url = urljoin(url, img_url)

            # 生成文件名（带 !lrg 后缀）
            filename_with_lrg = f"{title}_{idx}_!lrg{os.path.splitext(img_url)[1]}"
            save_path_with_lrg = os.path.join(album_dir, filename_with_lrg)

            # 提交下载任务到线程池
            future = executor.submit(download_image, img_url, save_path_with_lrg)
            futures.append(future)

        # 等待所有任务完成
        for future in tqdm(futures, desc="下载进度", ncols=80):
            future.result()

    print(f"下载完成：所有图片已保存到 {album_dir}")


# 修改 start_download 函数，添加进度条逻辑
def start_download():
    global progress_bar

    # 获取用户输入的 ID
    album_id = entry.get().strip()
    if not album_id:
        messagebox.showwarning("警告", "请输入相册 ID")
        return

    # 构建目标 URL
    target_url = f"https://www.girl-atlas.com/album?id={album_id}"

    # 显示正在下载的提示
    status_label.config(text="正在下载，请稍候...")
    root.update()

    # 重置进度条
    progress_var.set(0)
    progress_bar["value"] = 0

    # 使用多线程下载，避免阻塞 UI
    def download_task():
        try:
            # 获取高清图片 URL（!lrg）
            lrg_urls = get_dynamic_content(target_url)

            # 确保 URL 包含 !lrg 后缀
            valid_urls = [urljoin(target_url, url) for url in lrg_urls if '!lrg' in url]

            # 计算总任务数
            total_tasks = len(valid_urls)
            completed_tasks = 0

            # 解析相册标题
            html = requests.get(target_url).text
            soup = BeautifulSoup(html, 'html.parser')
            title = soup.find('h1').text.strip() if soup.find('h1') else "untitled"

            # 创建下载目录
            domain = urlparse(target_url).netloc
            save_dir = os.path.join("downloads", domain, title)
            os.makedirs(save_dir, exist_ok=True)

            # 多线程下载高清图片（!lrg）并重命名
            with ThreadPoolExecutor(max_workers=10) as executor:  # 使用线程池并行下载
                futures = []
                for idx, img_url in enumerate(valid_urls, 1):
                    # 生成文件名（带 !lrg 后缀）
                    filename_with_lrg = f"{title}_{idx}_!lrg{os.path.splitext(img_url)[1]}"
                    save_path_with_lrg = os.path.join(save_dir, filename_with_lrg)

                    # 提交下载任务到线程池
                    future = executor.submit(download_image, img_url, save_path_with_lrg)
                    futures.append(future)

                # 更新进度条
                for future in futures:
                    future.result()
                    completed_tasks += 1
                    progress_var.set(completed_tasks / total_tasks * 100)
                    progress_bar["value"] = progress_var.get()
                    root.update_idletasks()  # 刷新 UI

            status_label.config(text="下载完成！")
            messagebox.showinfo("成功", "所有图片已成功下载！")
        except Exception as e:
            status_label.config(text="下载失败，请检查 ID 或网络连接")
            messagebox.showerror("错误", f"下载过程中出现错误：{str(e)}")

    # 启动多线程任务
    threading.Thread(target=download_task, daemon=True).start()


# --------------------------------------

# 创建主窗口
root = tk.Tk()
root.title("PhotoDownloadToolsByXrb")
root.geometry("500x400")  # 调整窗口大小
root.resizable(False, False)  # 固定窗口大小

# 设置窗口图标（需要图标文件）
# root.iconbitmap("DM_20250209162117_001.ico")  # 替换为你的图标文件路径

# 设置窗口背景颜色
root.configure(bg="#f0f0f0")  # 浅灰色背景

# 全局变量，用于存储下载状态和进度
progress_var = tk.DoubleVar()
progress_bar = None

# 初始化进度条
progress_var.set(0)
progress_bar = ttk.Progressbar(root, variable=progress_var, maximum=100, length=400)
progress_bar.pack(fill=tk.X, padx=20, pady=10)

# 提示标签
tk.Label(root, text="请输入相册 ID：", font=("Arial", 12), bg="#f0f0f0", fg="black").pack(pady=(20, 5))

# 输入框
entry = tk.Entry(root, width=50, font=("Arial", 12), bd=2, relief=tk.SOLID)
entry.pack(pady=5)

# 下载按钮
download_button = tk.Button(root, text="开始下载", font=("Arial", 12, "bold"), bg="#87ceeb", fg="black",
                            activebackground="#45a049", activeforeground="white", command=start_download)
download_button.pack(pady=10)

# 状态标签
status_label = tk.Label(root, text="等待中...", fg="purple", bg="#f0f0f0", font=("Arial", 20, "italic"))
status_label.pack(pady=10)

# 添加超链接标签
def open_link(event):
    webbrowser.open("https://www.girl-atlas.com/")

link_label = tk.Label(root, text="测试官网(CTRL+鼠标左键->)", fg="blue", bg="#f0f0f0", font=("Arial", 12), cursor="hand2")
link_label.pack(pady=10)
link_label.bind("<Button-1>", open_link)

# 添加不可点击的信息文本
info_label = tk.Label(root, text="本软件开发仅支持上方网站\n只用于交流和学习", fg="gray", bg="#f0f0f0", font=("Arial", 10, "italic"))
info_label.pack(pady=5)


copyright_label = tk.Label(root, text="© 2025 xrb. All rights reserved.", fg="gray", bg="#f0f0f0",
                           font=("Arial", 8, "italic"))
copyright_label.pack(side=tk.BOTTOM, pady=5)

# 运行主循环
root.mainloop()

