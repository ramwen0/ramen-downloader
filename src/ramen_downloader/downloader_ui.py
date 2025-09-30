import customtkinter
import threading
from tkinter import filedialog
from .downloader_brains import Downloader

class DownloaderApp:
    def __init__(self):
        self.downloader = Downloader()
        self.download_directory = ''
        self.setup_ui()
        
    def setup_ui(self):
        # App Theme
        customtkinter.set_appearance_mode("system")
        customtkinter.set_default_color_theme(f"../themes/purple.json")  # built in themes are: blue, dark-blue, green

        self.root = customtkinter.CTk()
        self.root.geometry('600x550')
        self.root.title('Ramen URL Downloader')

        # Main frame
        self.frame = customtkinter.CTkFrame(master=self.root) 
        self.frame.pack(pady=20, padx=60, fill='both', expand=True)

        # Title Label
        self.label = customtkinter.CTkLabel(master=self.frame, text="Ramen's URL Downloader", font=('Roboto', 24))
        self.label.pack(pady=12, padx=10)

        # Entry for URL
        self.url_entry = customtkinter.CTkEntry(master=self.frame, placeholder_text='Insert the URL here', width=400)
        self.url_entry.pack(pady=12, padx=10)

        # Button to browse for a directory
        self.browse_button = customtkinter.CTkButton(master=self.frame, text="Browse Download Location", command=self.browse_directory)
        self.browse_button.pack(pady=12, padx=10)

        # Label to display the selected download directory
        self.dir_label = customtkinter.CTkLabel(master=self.frame, text="Download location: Not selected")
        self.dir_label.pack(pady=12, padx=10)

        # Progress bar with percentage label
        self.progress_frame = customtkinter.CTkFrame(master=self.frame, fg_color="transparent")
        self.progress_frame.pack(pady=12, padx=10)

        self.progress_bar = customtkinter.CTkProgressBar(master=self.progress_frame, width=400, height=10)
        self.progress_bar.pack(side='left', padx=(0, 10))
        self.progress_bar.set(0)

        self.progress_percentage_label = customtkinter.CTkLabel(master=self.progress_frame, text="0%", width=40)
        self.progress_percentage_label.pack(side='right')

        # Status label - shows current activity
        self.status_label = customtkinter.CTkLabel(master=self.frame, text="Ready to download", wraplength=480)
        self.status_label.pack(pady=5, padx=10)

        # Button frame for side-by-side buttons
        self.button_frame = customtkinter.CTkFrame(master=self.frame, fg_color="transparent")
        self.button_frame.pack(pady=12, padx=10)

        # Submit button for the form
        self.submit_button = customtkinter.CTkButton(master=self.button_frame, text='Download', command=self.convert)
        self.submit_button.pack(side='left', padx=5)

        # Cancel button
        self.cancel_button = customtkinter.CTkButton(
            master=self.button_frame, 
            text='Cancel Download', 
            command=self.cancel_download,
            state="disabled",
            fg_color="#d9534f",
            hover_color="#c9302c"
        )
        self.cancel_button.pack(side='left', padx=5)

    def browse_directory(self):
        self.download_directory = filedialog.askdirectory()
        if self.download_directory:
            self.dir_label.configure(text=f"Download location: {self.download_directory}")
        else:
            self.download_directory = '.'

    def convert(self):
        url = self.url_entry.get().strip()
        if not url:
            from tkinter import messagebox
            messagebox.showwarning("Input Error", "Please enter a valid URL")
            return

        if not self.download_directory:
            from tkinter import messagebox
            messagebox.showwarning("Directory Error", "Please select a download location")
            return

        # Reset progress bar to 0
        self.progress_bar.set(0)
        self.progress_percentage_label.configure(text="0%")
        self.status_label.configure(text="Starting download...")
        
        # Enable cancel button and disable submit
        self.cancel_button.configure(state="normal")
        self.submit_button.configure(state="disabled")

        def update_progress(total_progress, current_track, total_tracks, track_name, track_progress):
            self.progress_bar.set(total_progress / 100)
            self.progress_percentage_label.configure(text=f"{total_progress:.1f}%")
            
            status_text = f"({current_track}/{total_tracks}) {track_name}"
            if track_progress > 0:
                status_text += f" - {track_progress:.1f}%"
            self.status_label.configure(text=status_text)
            
            self.root.update_idletasks()

        download_thread = threading.Thread(
            target=self.downloader.download_playlist_as_mp3, 
            args=(url, self.download_directory, update_progress, lambda text: self.status_label.configure(text=text))
        )
        download_thread.daemon = True
        download_thread.start()
        
        def check_thread():
            if download_thread.is_alive():
                self.root.after(100, check_thread)
            else:
                self.submit_button.configure(state="normal")
                self.cancel_button.configure(state="disabled")
        
        self.root.after(100, check_thread)

    def cancel_download(self):
        self.downloader.cancel_download_func()
        self.status_label.configure(text="Cancelling download...")

    def run(self):
        self.root.mainloop()