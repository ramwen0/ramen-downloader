# Maintainer: Your Name <your@email.com>
pkgname=ramen-downloader
pkgver=1.0.0
pkgrel=1
pkgdesc="A simple YouTube playlist downloader"
arch=('any')
url="https://github.com/yourusername/ramen-downloader"
license=('MIT')
depends=(
    'python'
    'python-customtkinter'
    'yt-dlp'
    'python-pillow'
    'ffmpeg'  # Required for audio conversion
    'tk'      # Required for filedialog
)
source=("$pkgname-$pkgver.tar.gz")
sha256sums=('SKIP')  # Replace with actual checksum

package() {
    cd "$srcdir/$pkgname-$pkgver"
    
    # Install Python package
    python setup.py install --root="$pkgdir" --optimize=1
    
    # Install desktop file
    install -Dm644 "$pkgname.desktop" "$pkgdir/usr/share/applications/$pkgname.desktop"
    
    # Install icon (if you have one)
    # install -Dm644 "assets/icon.png" "$pkgdir/usr/share/pixmaps/$pkgname.png"
    
    # Install README
    install -Dm644 README.md "$pkgdir/usr/share/doc/$pkgname/README.md"
}