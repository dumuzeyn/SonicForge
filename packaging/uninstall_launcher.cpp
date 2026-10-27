#include <windows.h>
#include <shellapi.h>
#include <string>
#include <vector>

namespace {
constexpr wchar_t uninstallKey[] =
    L"Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\"
    L"{1B9EA71F-7D06-4F35-88B7-F71B12642E50}_is1";

bool isFile(const std::wstring& path) {
    const DWORD attributes = GetFileAttributesW(path.c_str());
    return attributes != INVALID_FILE_ATTRIBUTES && !(attributes & FILE_ATTRIBUTE_DIRECTORY);
}

std::wstring findUninstaller(HKEY root, REGSAM view) {
    HKEY key = nullptr;
    if (RegOpenKeyExW(root, uninstallKey, 0, KEY_QUERY_VALUE | view, &key) != ERROR_SUCCESS)
        return {};
    DWORD bytes = 0;
    LONG result = RegGetValueW(key, nullptr, L"UninstallString", RRF_RT_REG_SZ,
                              nullptr, nullptr, &bytes);
    std::vector<wchar_t> value(bytes / sizeof(wchar_t) + 1, L'\0');
    if (result == ERROR_SUCCESS)
        result = RegGetValueW(key, nullptr, L"UninstallString", RRF_RT_REG_SZ,
                              nullptr, value.data(), &bytes);
    RegCloseKey(key);
    if (result != ERROR_SUCCESS || bytes == 0) return {};

    int count = 0;
    wchar_t** arguments = CommandLineToArgvW(value.data(), &count);
    std::wstring path;
    if (arguments && count == 1) path = arguments[0];
    if (arguments) LocalFree(arguments);
    const auto separator = path.find_last_of(L"\\/");
    if (separator == std::wstring::npos) return {};
    const std::wstring name = path.substr(separator + 1);
    // An Inno uninstaller needs its installation-specific log beside the EXE.
    if (name.size() < 12 || name.substr(0, 5) != L"unins" ||
        name.substr(name.size() - 4) != L".exe" ||
        name.find_first_not_of(L"0123456789", 5) != name.size() - 4)
        return {};
    if (!isFile(path) || !isFile(path.substr(0, path.size() - 4) + L".dat")) return {};
    return path;
}
}

int WINAPI wWinMain(HINSTANCE, HINSTANCE, PWSTR commandLine, int) {
    const bool checkOnly = std::wstring(commandLine) == L"--check";
    if (*commandLine && !checkOnly) return 1;
    std::wstring uninstaller;
    for (const HKEY root : {HKEY_CURRENT_USER, HKEY_LOCAL_MACHINE}) {
        for (const REGSAM view : {KEY_WOW64_64KEY, KEY_WOW64_32KEY}) {
            uninstaller = findUninstaller(root, view);
            if (!uninstaller.empty()) break;
        }
        if (!uninstaller.empty()) break;
    }
    if (uninstaller.empty()) {
        if (!checkOnly)
            MessageBoxW(nullptr,
                L"Установленная версия Sonic Forge не найдена.\n"
                L"Если файлы установки были перемещены, повторите установку и запустите удаление снова.",
                L"Удаление Sonic Forge", MB_OK | MB_ICONINFORMATION);
        return 2;
    }
    if (checkOnly) return 0;
    // Keep Inno Setup's normal confirmation and running-application checks.
    SHELLEXECUTEINFOW execute{};
    execute.cbSize = sizeof(execute);
    execute.fMask = SEE_MASK_NOCLOSEPROCESS;
    execute.lpVerb = L"open";
    execute.lpFile = uninstaller.c_str();
    execute.nShow = SW_SHOWNORMAL;
    if (!ShellExecuteExW(&execute)) {
        if (GetLastError() != ERROR_CANCELLED)
            MessageBoxW(nullptr, L"Не удалось запустить удаление Sonic Forge.",
                        L"Удаление Sonic Forge", MB_OK | MB_ICONERROR);
        return 3;
    }
    if (execute.hProcess) CloseHandle(execute.hProcess);
    return 0;
}
