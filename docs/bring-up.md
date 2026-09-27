# Реална връзка A2 — 2026-09-26

Работна директория: `F:/fpga/A2`. Не е използван старият локален SPI код.

## Най-ново състояние: графика и двоичен USB обмен

Windows показва HIRES/LORES, двете страници и MIXED. CPU изпълнява графичния
тест от `host/graphics_demo.py` и сам рисува движещата се фигура. FPGA образът
е същият endpoint v2; за тази стъпка не е препрограмиран.
Pico вече изпълнява `pico/binary_bridge.py` в RAM, със същия PIO 2 MHz SPI.
Текущият прозорец и CLI клиентите изискват двоичен транспорт.
Виж [графика](graphics.md) и [USB протокол и възстановяване](binary-transport.md).

## Предходен етап: жив Windows текстов екран

В SRAM е endpoint v2 с двупортова RAM, Apple II keyboard latch и видео
soft switches. CPU изпълнява нашия текстов тест на 1 MHz. Windows прозорецът
чете живия екран и изпраща клавиши само от фокусираното поле.
Проверките на платката и на прозореца минаха; [подробности](live-display.md).
Pico е същият PIO 2 MHz мост на COM7. Flash отново не е променян.
Докато прозорецът работи, той държи COM7; затвори го преди CLI тестове.

## Актуализация: процесорът вече е проверен на платката

FPGA SRAM вече съдържа новото 6502 ядро, 48 KiB основна RAM и 4 KiB тестова
памет. Пълният тест на Klaus Dormann мина за 96,4 s на 1 MHz; всички 52 KiB
минаха запис/прочит. CPU е спрян в успешния краен цикъл, тестът е в RAM.
Pico продължава да работи като PIO мост на COM7. Flash не е променян.
Подробности: [CPU и памет](cpu.md), отчет `build/hardware/cpu.json`.
Екранът, клавиатурата и Disk II все още предстоят.

## Предишно състояние: само диагностична връзка

- FPGA SRAM: `a2_link_top`, новият диагностичен дизайн.
- Pico #2: новият мост в MicroPython RAM, PIO0 SM0, SPI 2 MHz, COM7.
- FPGA конфигурационният флаш и файловете в Pico flash не са записвани.
- CPU 6502, RAM карта, Disk II и Windows видео прозорец още не са реализирани.
- Целта остава оригиналната Karateka за Apple II (1984), без BASIC като
  самостоятелен етап.

## Резултати

| Проверка | Резултат |
|---|---|
| Native build за AG10KL144H | 0 errors, 0 warnings |
| Изводи и I/O standard | всичките 7 съвпадат; 3.3-V LVTTL |
| Вътрешен clock | 50 MHz constraint, setup slack +9.076 ns, hold +0.550 ns |
| Диагностика с GPIO master | идентичност, шаблон, unknown opcode и 100 echo пакета — PASS |
| PIO/DMA локален тест | 16×4096 payload bytes на всяка от 4 честоти — PASS |
| PIO 100 kHz | 12469 полезни bytes/s |
| PIO 500 kHz | 61594 полезни bytes/s |
| PIO 1 MHz | 121053 полезни bytes/s |
| PIO 2 MHz | 237057 полезни bytes/s |
| Windows JSON, малки пакети | 1000×62 payload bytes, 0 грешки, 1909 bytes/s (преди оптимизацията) |
| Windows JSON, големи пакети | 32×8192 bytes, 0 грешки, 9369 bytes/s (междинен вариант) |
| Windows JSON, оптимизиран | 8×8192 bytes, 0 грешки, 18285 bytes/s |
| Брояч във FPGA | нараства; snapshot read работи |
| Python тестове | 17 PASS |

SPI throughput е измерен локално на Pico, без USB и JSON. End-to-end
числата включват двупосочен echo, Windows клиента, USB, JSON и SPI;
те не са измерена скорост на видеопоток. JSON остава тесният участък.

Времевият отчет покрива вътрешния 50 MHz clock. Асинхронните SPI
входове и външните изходи са изключени от синхронния timing анализ;
практическите SPI скорости са проверени чрез реалния пренос.

## JTAG несъответствие — отворено

`af.exe --prg a2_link_sram.prg` отчете `Scanned data did not match
expected value`. Инструментът е оставен да връща неуспех при тази грешка;
не сме махали проверки или маски. Въпреки това новият A2 протокол
работи на физическата платка след записа. Това е независима функционална
проверка, не доказателство за успешно JTAG readback сравнение на всички битове.
Точната причина остава неизяснена. Лог: `build/fpga/program.log`.

## Възстановяване

Karateka вече използва файлов адаптер през SPI (виж `karateka.md`), без
Disk II. Последният FPGA образ добавя освободени входове за липсващите
бутони `$C060..C063`; компилация 2058 LUT / 446 FF / 52 BRAM, final setup
+5.607 ns и hold +0.292 ns. Програмиран е само SRAM. JTAG readback mismatch
остава отчетен, а работещите нови входове и играта са проверени през SPI.
Външните данни се възстановяват с `python tools/fetch_karateka.py`.

Текущият Windows клиент използва `A2S!` снимки от новия Pico binary мост,
ограничени до 10/s. За самите снимки не се променя FPGA bitstream. При по-стар зареден Pico
мост го презареди с командата по-долу; графичното демо се зарежда от бутона
„Графика“. Проверени са цели движещи се кадри и запазване на ръчната пауза:
`build/hardware/snapshot.json`, подробности в `graphics.md`.

```powershell
python tools/build_fpga.py
python host/pico_repl.py --port COM7 --idle
python tools/program_fpga.py
```

При JTAG mismatch не приемай автоматично записът за успешен. В тази
сесия след него направихме отделна функционална проверка с:

```powershell
python host/pico_repl.py --port COM7 --start-bridge --backend pio --spi-hz 2000000
python host/diagnose.py --port COM7 --rounds 100 --payload-size 62
```

Тест на PIO без USB разход:

```powershell
python host/benchmark_pio.py --port COM7
```

Той спира текущия мост и завършва в REPL; след него стартирай моста отново.
Изключването на захранването губи и FPGA SRAM дизайна, и Pico RAM кода.

## Файлове с измервания

- `build/hardware/pio-benchmark.json`
- `build/hardware/windows-pio-diagnostic.json`
- `build/hardware/windows-block-diagnostic.json`
- `build/hardware/windows-block-diagnostic-optimized.json`
- `build/fpga/alta_logs/run.log`
- `build/fpga/alta_db/io.asf`

SDK капаните, отстранени в новия build скрипт: setup генерира и
презаписва QSF; native flow изисква VE pin map преди packing; процесът
може да върне exit code 0 въпреки `Error:` в лога. Проверяваме и текста.

PIO/DMA API справки:
- https://docs.micropython.org/en/v1.29.0/library/rp2.StateMachine.html
- https://docs.micropython.org/en/v1.29.0/library/rp2.DMA.html
