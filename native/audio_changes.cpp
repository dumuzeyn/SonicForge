#include "core.h"
#include <cmath>
#include <cstring>

namespace sf {
QList<QPair<double, double>> audioChanges(const QString& original, const QString& modified,
                                        const Cancel& cancel) {
    checkpoint(cancel);
    if (original == modified)
        return {};
    // Decode together in output-time order: processed L/R, original L/R.
    // Pad the original so a longer reverb tail is included, and stop at the
    // processed file's end. Streaming keeps memory independent of song length.
    constexpr int rate = 44100, frameSamples = rate / 20;
    constexpr int sampleBytes = 4 * sizeof(float), frameBytes = frameSamples * sampleBytes;
    QProcess decoder;
    decoder.setProgram(executable("ffmpeg"));
    decoder.setArguments({
        "-hide_banner", "-nostdin", "-v", "error", "-protocol_whitelist", "file,pipe", "-i", original, "-protocol_whitelist", "file,pipe", "-i", modified,
        "-filter_complex",
        "[0:a]aresample=44100,aformat=sample_fmts=flt:channel_layouts=stereo,apad[o];"
        "[1:a]aresample=44100,aformat=sample_fmts=flt:channel_layouts=stereo[p];"
        "[p][o]join=inputs=2:channel_layout=quad:map=0.0-FL|0.1-FR|1.0-BL|1.1-BR[out]",
        "-map", "[out]", "-c:a", "pcm_f32le", "-f", "f32le", "pipe:1"});
#ifdef Q_OS_WIN
    decoder.setCreateProcessArgumentsModifier(
        [](QProcess::CreateProcessArguments* args) { args->flags |= 0x08000000; });
#endif
    decoder.start();
    if (!decoder.waitForStarted(15000))
        throw Error(decoder.errorString());
    adoptChild(decoder);
    QList<QPair<double, double>> ranges;
    qint64 samples = 0;
    auto compare = [&](const char* data, int bytes) {
        const int count = bytes / sampleBytes;
        double difference = 0, reference = 0;
        for (int i = 0; i < count; ++i) {
            float channels[4];
            std::memcpy(channels, data + i * sampleBytes, sampleBytes);
            for (int channel = 0; channel < 2; ++channel) {
                double processed = channels[channel], input = channels[channel + 2];
                if (!std::isfinite(processed) || !std::isfinite(input))
                    continue;
                difference += (processed - input) * (processed - input);
                reference += qMax(processed * processed, input * input);
            }
        }
        double start = samples / double(rate), end = (samples + count) / double(rate);
        // Ignore quantization and very small differences; retain actual changes
        // to quiet passages and differences between left and right channels.
        if (count > 0 && difference / (count * 2) > 1e-8 &&
            difference > reference * .0001) {
            if (!ranges.isEmpty() && start - ranges.last().second < .051)
                ranges.last().second = end;
            else
                ranges << qMakePair(start, end);
        }
        samples += count;
    };
    QByteArray pending, errors;
    QElapsedTimer idle, elapsed; idle.start(); elapsed.start();
    try {
        do {
            checkpoint(cancel);
            decoder.waitForReadyRead(30);
            if (idle.elapsed() > 60000 || elapsed.elapsed() > 6 * 60 * 60 * 1000) throw Error("Превышено время сравнения звука");
            errors = (errors + decoder.readAllStandardError()).right(4096);
            const auto bytes = decoder.read(65536); if (!bytes.isEmpty()) idle.restart(); pending += bytes;
            int consumed = 0;
            while (consumed + frameBytes <= pending.size()) {
                compare(pending.constData() + consumed, frameBytes);
                consumed += frameBytes;
            }
            pending.remove(0, consumed);
        } while (decoder.state() != QProcess::NotRunning || decoder.bytesAvailable() > 0);
        if (decoder.exitStatus() != QProcess::NormalExit || decoder.exitCode() != 0)
            throw Error(QString::fromUtf8(errors));
        if (!pending.isEmpty())
            compare(pending.constData(), pending.size());
        checkpoint(cancel);
    } catch (...) {
        decoder.kill();
        decoder.waitForFinished(1000);
        throw;
    }
    return ranges;
}
}
