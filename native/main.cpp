#include "window.h"
#include <cstdio>
int main(int argc, char** argv) {
    Q_INIT_RESOURCE(resources);
    Q_INIT_RESOURCE(help_resource);
    QStringList arguments;
    for (int i = 0; i < argc; ++i)
        arguments << QString::fromLocal8Bit(argv[i]);
    if (arguments.contains("--speech-worker") || arguments.contains("--stems-worker")) {
        QCoreApplication application(argc, argv);
        QCoreApplication::setApplicationName("SonicForge");
        QCoreApplication::setOrganizationName("Dumuzeyn");
        return sf::neuralWorker(application.arguments());
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
    QApplication application(argc, argv);
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
    QStringList files;
    for (int i = 1; i < arguments.size(); ++i)
        if (!arguments[i].startsWith('-') && QFileInfo(arguments[i]).isFile())
            files << arguments[i];
    int smoke = arguments.indexOf("--smoke-test");
    int playback = arguments.indexOf("--playback-smoke");
    int result = arguments.indexOf("--result");
    if (playback >= 0 && playback + 1 < arguments.size() && result >= 0 &&
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
        QTimer::singleShot(0, &window, [&window, files] { window.openFiles(files); });
    return application.exec();
}
