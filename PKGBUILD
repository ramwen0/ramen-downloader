# Maintainer: Your Name <your@email.com>
pkgname=ramen_downloader
pkgver=1.0.0
pkgrel=1
pkgdesc="A simple YouTube playlist downloader"
arch=('any')
url="https://github.com/ramwen0/ramen-downloader"
license=('MIT-0')
depends=(
    'python'
    'python-customtkinter'
    'yt-dlp'
    'python-pillow'
    'ffmpeg'  # Required for audio conversion
    'tk'      # Required for filedialog
)
source=("https://github.com/ramwen0/ramen-downloader")
sha256sums=('cdacfc09b88e87b1ecdf79553f9d4a915301a3efeb9bfc219a2765d79dc396ec')

package() {
    cd "../"
    
    # Install Python package
    python setup.py install --root="$pkgdir" --optimize=1
    
    # Install desktop file
    install -Dm644 "$pkgname.desktop" "$pkgdir/usr/share/applications/$pkgname.desktop"
    
    # Install icon (if you have one)
    # install -Dm644 "assets/icon.png" "$pkgdir/usr/share/pixmaps/$pkgname.png"
    
    # Install README
    install -Dm644 README.md "$pkgdir/usr/share/doc/$pkgname/README.md"

    # Install license
    install -Dm644 LICENSE "${pkgdir}/usr/share/licenses/${pkgname}/MIT-0"
}
