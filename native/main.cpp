#include "window.h"
#include "build_info.h"
#include <cstdio>
class SafeApplication final : public QApplication {
  public:
    using QApplication::QApplication;
    bool notify(QObject* receiver, QEvent* event) override {
        try { return QApplication::notify(receiver, event); }
        catch (const std::exception& error) { QMessageBox::warning(nullptr, "Sonic Forge", QString::fromUtf8(error.what())); }
        catch (...) { QMessageBox::warning(nullptr, "Sonic Forge", "Не удалось выполнить действие. Изменения проекта сохранены в памяти."); }
        return false;
    }
};
#ifdef Q_OS_WIN
#include <shobjidl.h>
#include <windows.h>
#endif
int main(int argc, char** argv) {
#ifdef Q_OS_WIN
    const HANDLE installLease = CreateMutexW(nullptr, FALSE, L"Local\\Dumuzeyn.SonicForge.InstallLock");
    const auto releaseLease = qScopeGuard([&] { if (installLease) CloseHandle(installLease); });
#endif
    Q_INIT_RESOURCE(resources);
    Q_INIT_RESOURCE(help_resource);
    Q_INIT_RESOURCE(brand_resource);
    Q_INIT_RESOURCE(check_resource);
    QStringList arguments;
    for (int i = 0; i < argc; ++i)
        arguments << QString::fromLocal8Bit(argv[i]);
    if (arguments.contains("--version")) { std::puts("Sonic Forge " SF_VERSION " " SF_SOURCE_DIGEST); return 0; }
    if (arguments.contains("--build-info")) {
        QCoreApplication app(argc, argv); const auto args = app.arguments(); const int index = args.indexOf("--build-info");
        if (index + 1 >= args.size()) return 2;
        QSaveFile output(args[index + 1]);
        if (!output.open(QIODevice::WriteOnly)) return 2;
        output.write(QJsonDocument(QJsonObject{{"version", SF_VERSION}, {"sourceDigest", SF_SOURCE_DIGEST}, {"qt", qVersion()}, {"architecture", QSysInfo::buildCpuArchitecture()}}).toJson());
        return output.commit() ? 0 : 2;
    }
    if (arguments.contains("--help")) { std::puts("SonicForge.exe [audio files | project.sfproject] [--version]\nDiagnostics: --smoke-test DIRECTORY, --reliability-smoke --result FILE"); return 0; }
    const QSet<QString> accepted{"--speech-worker", "--stems-worker", "--diagnose-cover-rhythm", "--diagnose-audio", "--smoke-test", "--playback-smoke", "--lyrics-save-smoke", "--cover-export-smoke", "--close-smoke", "--sound-smoke", "--reliability-smoke", "--result", "--cover-image", "--audio", "--model", "--language", "--align", "--reference", "--out", "--segment-seconds", "--ctc-only", "--ctc-direct", "--verify-recognition", "--fast", "--trace-words"};
    for (const auto& arg : arguments.mid(1)) if (arg.startsWith("--") && !accepted.contains(arg)) { std::fprintf(stderr, "Unknown option: %s\n", arg.toUtf8().constData()); return 2; }
    if (arguments.contains("--speech-worker") || arguments.contains("--stems-worker")) {
        QCoreApplication application(argc, argv);
        QCoreApplication::setApplicationName("SonicForge");
        QCoreApplication::setOrganizationName("Dumuzeyn");
        return sf::neuralWorker(application.arguments());
    }
    if (arguments.contains("--diagnose-cover-rhythm")) {
        QGuiApplication application(argc, argv);
        const auto args=application.arguments();
        const int input=args.indexOf("--diagnose-cover-rhythm"), result=args.indexOf("--result"), picture=args.indexOf("--cover-image");
        if (input+1>=args.size() || result<0 || result+1>=args.size()) return 2;
        try {
            auto report=sf::analyzeCoverRhythm(args[input+1]);
            if (picture>=0 && picture+1<args.size()) {
                sf::CoverOptions options;
                options.size=512;options.colorSource=2;options.title=options.symbol=false;
                if (!sf::makeCover(args[input+1],{},options).save(args[picture+1])) return 2;
            }
            QFile file(args[result+1]);
            if (!file.open(QIODevice::WriteOnly)) return 2;
            file.write(QJsonDocument(report).toJson());
            return 0;
        } catch (const std::exception& error) { std::fprintf(stderr,"%s\n",error.what()); return 1; }
    }
    if (arguments.contains("--diagnose-audio")) {
        QCoreApplication application(argc, argv);
        QCoreApplication::setApplicationName("SonicForge");
        QCoreApplication::setOrganizationName("Dumuzeyn");
        auto args = application.arguments();
        int input = args.indexOf("--diagnose-audio"), output = args.indexOf("--result");
        if (input + 1 >= args.size() || output < 0 || output + 1 >= args.size())
            return 2;
        QJsonObject result;
        int code = 0;
        try {
            auto source = sf::readSource(args[input + 1]);
            result = sf::analyze(source.path);
            result["duration"] = source.duration;
            result["genre"] = sf::genre(source.path);
            result["ffmpeg"] = sf::executable("ffmpeg");
            result["plugins"] = QJsonArray::fromStringList(QCoreApplication::libraryPaths());
        } catch (const std::exception& error) {
            result["error"] = QString::fromUtf8(error.what());
            code = 1;
        }
        QFile file(args[output + 1]);
        if (!file.open(QIODevice::WriteOnly))
            return 2;
        file.write(QJsonDocument(result).toJson());
        return code;
    }
#ifdef Q_OS_WIN
    SetCurrentProcessExplicitAppUserModelID(L"Dumuzeyn.SonicForge");
#endif
    SafeApplication application(argc, argv);
    QCoreApplication::setApplicationVersion(SF_VERSION);
    bool testing = false;
    for (const auto& arg : application.arguments()) testing |= arg.contains("smoke") || arg == "--smoke-test";
    application.setProperty("sfTesting", testing);
    if (testing) {
        QSettings::setDefaultFormat(QSettings::IniFormat);
        const auto settings = QDir::tempPath() + "/SonicForge-tests-" + QString::number(QCoreApplication::applicationPid());
        QDir().mkpath(settings); QSettings::setPath(QSettings::IniFormat, QSettings::UserScope, settings);
        QStandardPaths::setTestModeEnabled(true);
    }
    application.setProperty("sfSkipRecovery", application.arguments().size() > 1);
    application.setQuitOnLastWindowClosed(true);
    application.setWindowIcon(QIcon(":/assets/sonic_forge_mark.ico"));
    arguments = application.arguments();
    QApplication::setStyle("Fusion");
    QDir fonts(QCoreApplication::applicationDirPath() + "/assets/fonts");
    if (!fonts.exists())
        fonts = QDir(QDir::currentPath() + "/assets/fonts");
    for (const auto& name : fonts.entryList({"*.ttf"}, QDir::Files))
        QFontDatabase::addApplicationFont(fonts.filePath(name));
    if (QFontDatabase::families().contains("Noto Sans"))
        application.setFont(QFont("Noto Sans", 10));
    Window window;
    window.show();
#ifdef Q_OS_WIN
    const auto handle = reinterpret_cast<HWND>(window.winId());
    auto instance = GetModuleHandleW(nullptr);
    SendMessageW(handle, WM_SETICON, ICON_BIG,
                 reinterpret_cast<LPARAM>(LoadImageW(instance, MAKEINTRESOURCEW(1), IMAGE_ICON,
                                                     GetSystemMetrics(SM_CXICON),
                                                     GetSystemMetrics(SM_CYICON), LR_SHARED)));
    SendMessageW(handle, WM_SETICON, ICON_SMALL,
                 reinterpret_cast<LPARAM>(LoadImageW(instance, MAKEINTRESOURCEW(1), IMAGE_ICON,
                                                     GetSystemMetrics(SM_CXSMICON),
                                                     GetSystemMetrics(SM_CYSMICON), LR_SHARED)));
#endif
    QStringList files;
    for (int i = 1; i < arguments.size(); ++i)
        if (!arguments[i].startsWith('-') && QFileInfo(arguments[i]).isFile())
            files << arguments[i];
    int smoke = arguments.indexOf("--smoke-test");
    int playback = arguments.indexOf("--playback-smoke");
    int result = arguments.indexOf("--result");
    int sound = arguments.indexOf("--sound-smoke");
    int saveLyrics = arguments.indexOf("--lyrics-save-smoke");
    int coverExport = arguments.indexOf("--cover-export-smoke");
    if (arguments.contains("--reliability-smoke") && result >= 0 && result + 1 < arguments.size()) {
        QTimer::singleShot(100, &window, [&window, arguments, result] { window.reliabilitySmoke(arguments[result + 1]); });
    } else if (coverExport >= 0 && coverExport + 1 < arguments.size() && result >= 0 && result + 1 < arguments.size()) {
        QTimer::singleShot(100, &window, [&window, arguments, result, coverExport] {
            window.coverExportSmoke(arguments[coverExport + 1], arguments[result + 1]);
        });
    } else if (saveLyrics >= 0 && saveLyrics + 1 < arguments.size() && result >= 0 && result + 1 < arguments.size()) {
        QTimer::singleShot(100, &window, [&window, arguments, result, saveLyrics] {
            window.lyricsSaveSmoke(arguments[saveLyrics + 1], arguments[result + 1]);
        });
    } else if (arguments.contains("--close-smoke") && result >= 0 && result + 1 < arguments.size()) {
        QTimer::singleShot(100, &window, [&window, arguments, result] {
            window.closeSmoke(arguments[result + 1]);
        });
    } else if (sound >= 0 && sound + 1 < arguments.size() && result >= 0 &&
               result + 1 < arguments.size()) {
        QTimer::singleShot(100, &window, [&window, arguments, result, sound] {
            window.soundSmoke(arguments[sound + 1], arguments[result + 1]);
        });
    } else if (playback >= 0 && playback + 1 < arguments.size() && result >= 0 &&
               result + 1 < arguments.size()) {
        QTimer::singleShot(100, &window, [&window, arguments, playback, result] {
            window.playbackSmoke(arguments[playback + 1], arguments[result + 1]);
        });
    } else if (smoke >= 0 && smoke + 1 < arguments.size()) {
        QString output = arguments[smoke + 1];
        QTimer::singleShot(300, &window, [&application, &window, output] {
            bool ok = window.smokeTest(output);
            application.exit(ok ? 0 : 1);
        });
    } else if (!files.isEmpty())
        QTimer::singleShot(0, &window, [&window, files] { if (files.first().endsWith(".sfproject", Qt::CaseInsensitive)) window.openProject(files.first()); else window.openFiles(files); });
    return application.exec();
}
