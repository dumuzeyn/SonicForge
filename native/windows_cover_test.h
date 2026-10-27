#pragma once
#include <QString>
#include <QDir>
#include <QFileInfo>
#ifdef Q_OS_WIN
#include <shobjidl.h>
inline bool windowsReadsCover(const QString& path) {
    HRESULT initialized = CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED);
    IShellItemImageFactory* factory = nullptr;
    QString native = QDir::toNativeSeparators(QFileInfo(path).absoluteFilePath());
    HRESULT result = SHCreateItemFromParsingName(
        reinterpret_cast<LPCWSTR>(native.utf16()), nullptr,
        IID_IShellItemImageFactory, reinterpret_cast<void**>(&factory));
    bool valid = false;
    if (SUCCEEDED(result)) {
        HBITMAP bitmap = nullptr;
        result = factory->GetImage(SIZE{256, 256}, SIIGBF_THUMBNAILONLY, &bitmap);
        if (SUCCEEDED(result) && bitmap) {
            BITMAP info{};
            valid = GetObject(bitmap, sizeof(info), &info) && info.bmWidth > 0 && info.bmHeight > 0;
            DeleteObject(bitmap);
        }
        factory->Release();
    }
    if (SUCCEEDED(initialized)) CoUninitialize();
    return valid;
}
#endif
