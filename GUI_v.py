import os
import polib
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinterdnd2 import TkinterDnD, DND_FILES
import gigachatHandler
import urllib3
from dotenv import load_dotenv
import threading
import queue
import sys

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Словарь для унификации терминов
glossary = {
    "room": "комната",
    "day": "день",
    "days": "дней",
    "No room": "Нет комнаты",
    "{count} day": "{count} день",
    "{count} days": "{count} дней",
    "Upload failed": "Ошибка загрузки",
    "Edit Person": "Редактировать пользователя"
}

# Кэш для хранения переведённых строк
translation_cache = {}

class TranslatorApp(TkinterDnD.Tk):
    def __init__(self):
        super().__init__()
        self.title("PO File Translator")
        self.geometry("700x600")
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.queue = queue.Queue()
        self.translating = False
        self.po = None
        self.output_file = None
        self.translated_count = 0
        self.total_entries = 0
        self.giga_token = None
        self.continue_button_on = False
        self.is_over_text = False  # Флаг для отслеживания наведения на текстовые поля
        self.create_widgets()
        self.check_queue()

        # Привязываем событие прокрутки ко всему окну
        self.bind_all("<MouseWheel>", self.on_mousewheel)

    def create_widgets(self):
        # Создаём Canvas и Scrollbar
        self.canvas = tk.Canvas(self)
        self.scrollbar = tk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        # Создаём Frame, который будет содержать все виджеты
        self.main_frame = tk.Frame(self.canvas)

        # Добавляем Frame на Canvas
        self.canvas.create_window((0, 0), window=self.main_frame, anchor="nw")

        # Размещаем Canvas и Scrollbar
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        # Привязываем событие прокрутки
        self.main_frame.bind("<Configure>", self.on_frame_configure)

        # Поле для AUTH_TOKEN
        tk.Label(self.main_frame, text="AUTH_TOKEN:").pack(pady=5)
        self.token_entry = tk.Entry(self.main_frame, width=50, show="*")
        self.token_entry.pack(pady=5)
        tk.Button(self.main_frame, text="Проверить токен", command=self.validate_token).pack(pady=5)

        # Checkbox авто-подтверждения
        self.auto_confirm_var = tk.BooleanVar(value=False)
        tk.Checkbutton(self.main_frame, text="Авто-подтверждение продолжения", variable=self.auto_confirm_var).pack(pady=5)

        # Ввод размера пакета строк
        tk.Label(self.main_frame, text="Число строк на пакет:").pack(pady=5)
        self.batch_size_spinbox = tk.Spinbox(self.main_frame, from_=100, to=10000, width=5)
        self.batch_size_spinbox.pack(pady=5)

        # Область для drag-and-drop
        self.drop_area = tk.Label(self.main_frame, text="Перетащите .po файл сюда или выберите вручную", relief="sunken", height=3)
        self.drop_area.pack(fill="x", padx=10, pady=10)
        self.drop_area.drop_target_register(DND_FILES)
        self.drop_area.dnd_bind('<<Drop>>', self.drop_file)

        # Кнопки для выбора файлов
        tk.Button(self.main_frame, text="Выбрать входной файл", command=self.select_input_file).pack(pady=5)
        tk.Button(self.main_frame, text="Выбрать выходной файл", command=self.select_output_file).pack(pady=5)

        # Текстовое поле для вывода
        self.output_text = tk.Text(self.main_frame, height=15, width=80)
        self.output_text.pack(padx=10, pady=10)
        self.output_scrollbar = tk.Scrollbar(self.main_frame, command=self.output_text.yview)
        self.output_scrollbar.pack(side="right", fill="y")
        self.output_text.config(yscrollcommand=self.output_scrollbar.set)

        # Прогресс
        self.progress_label = tk.Label(self.main_frame, text="Прогресс: 0/0 записей")
        self.progress_label.pack(pady=5)
        self.progress_bar = ttk.Progressbar(self.main_frame, mode="determinate")
        self.progress_bar.pack(fill="x", padx=10, pady=5)

        # Кнопки управления
        self.start_button = tk.Button(self.main_frame, text="Запустить перевод", command=self.start_translation, state="disabled")
        self.start_button.pack(pady=5)
        self.continue_button = tk.Button(self.main_frame, text="Продолжить перевод", command=self.continue_translation, state="disabled")
        self.continue_button.pack(pady=5)
        self.stop_button = tk.Button(self.main_frame, text="Остановить", command=self.stop_translation, state="disabled")
        self.stop_button.pack(pady=5)

        # Привязываем события <Enter> и <Leave> к текстовым полям
        self.token_entry.bind("<Enter>", lambda e: self.set_over_text(True))
        self.token_entry.bind("<Leave>", lambda e: self.set_over_text(False))
        self.output_text.bind("<Enter>", lambda e: self.set_over_text(True))
        self.output_text.bind("<Leave>", lambda e: self.set_over_text(False))

    def on_frame_configure(self, event):
        # Обновляем область прокрутки Canvas при изменении размера Frame
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def set_over_text(self, value):
        self.is_over_text = value

    def on_mousewheel(self, event):
        if not self.is_over_text:
            # Определяем направление прокрутки
            if sys.platform == "darwin":
                # Для macOS
                scroll_direction = 1
            else:
                # Для Windows и Linux
                scroll_direction = -1
            self.canvas.yview_scroll(int(scroll_direction * (event.delta / 120)), "units")

    def validate_token(self):
        auth_token = self.token_entry.get()
        if not auth_token:
            messagebox.showerror("Ошибка", "Введите AUTH_TOKEN")
            return
        try:
            self.giga_token = gigachatHandler.get_giga_token(auth_token)
            messagebox.showinfo("Успех", "Токен валиден")
            self.start_button.config(state="normal")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Невалидный токен: {e}")

    def select_input_file(self):
        file_path = filedialog.askopenfilename(filetypes=[("PO files", "*.po")])
        if file_path:
            self.drop_area.config(text=f"Выбран файл: {file_path}")
            self.input_file = file_path

    def select_output_file(self):
        file_path = filedialog.asksaveasfilename(defaultextension=".po", filetypes=[("PO files", "*.po")])
        if file_path:
            self.output_file = file_path
            self.output_text.insert(tk.END, f"Выходной файл: {file_path}\n")

    def drop_file(self, event):
        file_path = event.data
        if file_path.endswith(".po"):
            self.input_file = file_path
            self.drop_area.config(text=f"Выбран файл: {file_path}")
        else:
            messagebox.showerror("Ошибка", "Пожалуйста, перетащите .po файл")

    def translate_text(self, text, is_plural=False, msgctxt=None):
        if text in glossary:
            return glossary[text]
        
        cache_key = (text, is_plural, msgctxt)
        if cache_key in translation_cache:
            return translation_cache[cache_key]
        
        prompt = (
            "Я делаю перевод для сайта Indico, который занимается онлайн организацией мероприятий (Лекций, конференций, встреч) "
            "Переведите следующий английский текст на русский, сохраняя единый стиль и терминологию. "
            "Используйте формальный стиль. Сохраняйте все плейсхолдеры, такие как %(variable)s или {variable}, и HTML-теги. "
            "Например, 'Hello, %(name)s' должно быть переведено как 'Здравствуйте, %(name)s', "
            "а '<a href=\"url\">link</a>' должно остаться без изменений. "
            "Но ни в коем случае не добавляй теги, если их нет в оригинальной строке. Ответ обязан быть одной строкой, без дополнительных обьяснений, мне нужен исключительно перевод текста с данными условиями. Не добавляй ничего от себя.  "
            "Следуйте этим примерам:"
            "'room' → 'комната'"
            "'No room' → 'Нет комнаты'"
            "'{count} day' → '{count} день'"
            "'{count} days' → '{count} дней'"
        )
        if is_plural:
            prompt += "Переведите во множественном числе. "
        if msgctxt:
            prompt += f"Контекст: {msgctxt}. "
        prompt += f"Текст: {text}"
        
        try:
            translation = gigachatHandler.get_chat_completion(self.giga_token, prompt).strip()
            translation_cache[cache_key] = translation
            return translation
        except Exception as e:
            self.output_text.insert(tk.END, f"Ошибка при переводе '{text}': {e}\n")
            with open("translation_errors.log", "a", encoding="utf-8") as log:
                log.write(f"Ошибка при переводе '{text}': {e}\n")
            return ""

    def start_translation(self):
        if not hasattr(self, "input_file"):
            messagebox.showerror("Ошибка", "Выберите входной .po файл")
            return
        if not self.output_file:
            messagebox.showerror("Ошибка", "Выберите выходной .po файл")
            return
        if not os.path.exists(self.input_file):
            messagebox.showerror("Ошибка", f"Файл {self.input_file} не найден")
            return
        
        try:
            self.batch_size = int(self.batch_size_spinbox.get())
        except ValueError:
            messagebox.showerror("Ошибка", "Неверный размер пакета")
            return

        self.translating = True
        self.start_button.config(state="disabled")
        self.stop_button.config(state="normal")
        self.continue_button.config(state="disabled")
        self.output_text.delete(1.0, tk.END)
        
        self.po = polib.pofile(self.input_file)
        self.total_entries = len(self.po)
        self.translated_count = 0
        self.current_entry_index = 0  # Инициализируем индекс текущей записи
        self.progress_bar["maximum"] = self.total_entries
        self.progress_label.config(text=f"Прогресс: 0/{self.total_entries} записей")
        
        plural_forms = self.po.metadata.get('Plural-Forms', 'nplurals=2;')
        self.nplurals = int(plural_forms.split(';')[0].split('=')[1].strip())
        
        threading.Thread(target=self.translate_thread, daemon=True).start()

    def translate_thread(self):
        # Начинаем с текущего индекса, а не с начала
        for i in range(self.current_entry_index, len(self.po)):
            if not self.translating:
                break
            
            entry = self.po[i]
            self.current_entry_index = i + 1  # Обновляем индекс текущей записи
            
            if entry.msgid_plural:
                if all(not entry.msgstr_plural.get(str(i), '') for i in range(self.nplurals)):
                    singular = self.translate_text(entry.msgid, msgctxt=entry.msgctxt)
                    plural = self.translate_text(entry.msgid_plural, is_plural=True, msgctxt=entry.msgctxt)
                    if singular and plural:
                        entry.msgstr_plural = {str(i): (singular if i == 0 else plural) for i in range(self.nplurals)}
                        self.translated_count += 1
                        self.queue.put(
                            f"Оригинал: {entry.msgid} / {entry.msgid_plural}\n"
                            f"Перевод: {singular} / {plural}\n"
                        )
            else:
                if not entry.msgstr:
                    translation = self.translate_text(entry.msgid, msgctxt=entry.msgctxt)
                    if translation:
                        entry.msgstr = translation
                        self.translated_count += 1
                        self.queue.put(f"[Переведено] {entry.msgid} → {translation}\n")
            
            self.queue.put("update_progress")
            
            # Пауза по пакету
            if self.translated_count > 0 and self.translated_count % self.batch_size == 0:
                if not self.auto_confirm_var.get():
                    self.translating = False
                    self.queue.put("pause")
                    self.continue_button.config(state="normal")
                    self.stop_button.config(state="normal")
                    return
        
        self.queue.put("done")

    def continue_translation(self):
        self.translating = True
        self.start_button.config(state="disabled")
        self.continue_button.config(state="disabled")
        self.stop_button.config(state="normal")
        threading.Thread(target=self.translate_thread, daemon=True).start()

    def stop_translation(self):
        self.translating = False
        self.po.save(self.output_file)
        self.output_text.insert(tk.END, f"\nФайл сохранён: {self.output_file}\n")
        self.output_text.insert(tk.END, f"Переведено {self.translated_count}/{self.total_entries} записей.\n")
        self.start_button.config(state="normal")
        self.stop_button.config(state="disabled")
        self.continue_button.config(state="disabled")

    def check_queue(self):
        try:
            message = self.queue.get_nowait()
            if message == "pause":
                self.output_text.insert(tk.END, f"\nПауза: переведено {self.translated_count}/{self.total_entries}\n")
                self.progress_bar["value"] = self.translated_count
                self.progress_label.config(text=f"Прогресс: {self.translated_count}/{self.total_entries} записей")
            elif message == "done":
                self.stop_translation()
            elif message == "update_progress":
                self.progress_bar["value"] = self.translated_count
                self.progress_label.config(text=f"Прогресс: {self.translated_count}/{self.total_entries} записей")
            else:
                self.output_text.insert(tk.END, message)
                self.output_text.see(tk.END)
        except queue.Empty:
            pass
        self.after(100, self.check_queue)

    def on_closing(self):
        if self.translating and messagebox.askyesno("Подтверждение", "Перевод выполняется. Остановить и сохранить?"):
            self.stop_translation()
        self.destroy()

if __name__ == "__main__":
    app = TranslatorApp()
    app.mainloop()