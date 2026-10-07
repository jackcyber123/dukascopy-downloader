DUKASCOPY HISTORICAL DATA DOWNLOADER V1

Isi:
- dukascopy_downloader_v1.py : aplikasi GUI
- run_downloader.bat          : launcher Windows

Cara pakai:
1. Install Python 3.x di Windows.
2. Jalankan run_downloader.bat.
3. Pilih symbol, tanggal mulai/akhir, Bid/Ask/Bid+Ask, dan folder output.
4. Untuk uji pertama gunakan BTCUSD satu hari.
5. Resume/skip existing chunks aktif secara default.

Catatan:
- V1 fokus pada historical tick.
- Download disimpan per jam sebagai CSV agar aman jika proses terputus.
- Data yang belum tersedia pada server akan dicatat sebagai MISS/FAILED.
- Untuk symbol yang belum ada di tabel price scale, isi angka scale secara manual.
- Jangan langsung menjalankan rentang multi-tahun sebelum tes 1 hari berhasil.
