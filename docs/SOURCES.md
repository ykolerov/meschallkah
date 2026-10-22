# Источники, границы применимости и изменения

## Исходное техническое задание

**D1_build_instructions.pdf**, v1.0, 13 октября 2026 г., 22 стр., «Drive D1: programmable magnetic-stirrer drive — Build, commissioning and operating instructions», IYPT 2027 Problem 10 “Air vortex”, setup S1.

Этот PDF был передан в беседе, но **не сохранён как двоичный файл в репозитории**. Здесь перенесены инженерные параметры и реализован заново программный функционал, а не дословная копия исходных приложений. В случае расхождений требуется проверять версии.

Соответствие частей:

| PDF | Репозиторий |
|---|---|
| 2 Requirements / 4 BOM / 6 Mechanical build | docs/HARDWARE.md |
| 5 Electrical build | docs/WIRING.md |
| 7 Software, 7.2 Commands, Appendix C | tmc2209_uart.py, sweep.py, disc_rate.py |
| 8 Acceptance tests T1–T9 / 9 Procedure | docs/COMMISSIONING.md |
| 10 Open items and risks | README.md, docs/HARDWARE.md |

Проект **не** включает геометрический анализ вихря и управление камерой — эти части находятся за пределами D1.

## Документация производителей

- [Analog Devices / Trinamic TMC2209 datasheet rev. 1.09](https://www.analog.com/media/en/technical-documentation/data-sheets/tmc2209_datasheet_rev1.09.pdf) — UART, VACTUAL, current regulation, чопперы, регистры и диагностика. PDF изначально использовал rev. 1.08.
- [BIGTREETECH TMC2209 pinout](https://github.com/bigtreetech/docs/blob/master/docs/TMC2209.md) — маркировка выводов, допустимые напряжения и ток модуля.
- [BIGTREETECH TMC2209 wiki](https://neo.bttwiki.com/en/docs/accessories-docs/tmc-driver/tmc-2209/) — Rsense=0,110 Ω, PDN UART, VREF.
- [Silicon Labs CP2102/CP2109 datasheet](https://www.silabs.com/documents/public/data-sheets/CP2102-9.pdf) — распиновка CP2102, логические уровни, сигналы UART.
- [pyserial API](https://pyserial.readthedocs.io/en/latest/pyserial_api.html) — COM, RTS/DTR, Rx/Tx.

## Предусмотренные исправления/особенности по сравнению с PDF

- Режим без LED является исходным: имеющийся CP2102 имеет только пять доступных контактов без RTS/DTR. Поддерживаются **необязательные** --marker rts/dtr при доработке адаптера.
- Добавлен явно видимый STOP risk: VACTUAL не сбрасывается автоматически при потере компьютера; EN-switch обязателен.
- Добавлены проверки входных диапазонов, CRC/IFCNT, проверка ошибок и коды возврата команд.
- Аппаратно не проверено. Simulator подтверждает только протокол, алгоритм разгона, CSV и обработку исключений — **не** момент, магнитное сцепление, реальный UART timing или безопасность.
- В документации усилены требования к механическому удержанию вращающихся магнитов.

Не внесено в конструкцию: BLDC, PID, энкодер, ESP32, новая камера, закрытый контур скорости. Они могут быть рассмотрены **только отдельной модификацией ТЗ**.

## Field revisions (22 October 2026)

The original PDF specifies CP2102 and 17HS4401. The assembled and tested prototype now uses FT232 and StepperOnline 17HE15-1504S. The wiring and README documents distinguish the original reference design from the current equipment and from unverified planned additions. An LM2596S-ADJ module, momentary EN pushbutton with 10 kΩ pullup, and FT232 RTS LED with a 100 Ω resistor are present in the reported assembly, but the newly soldered system is **not independently inspected**.

Earlier observations: physical TMC2209 version 0x21 over COM4, real motor rotation, tachometer 201.3 / 503 / 1005–1006 rpm for respective nominal 200 / 500 / 1000 rpm settings. These are user-reported bench measurements, **not manufacturer specifications or formal calibration**.

The driver remains open-loop. The optional `--no-tune` diagnostic option skips the StealthChop tune, which is not a replacement for validated startup and dynamic tuning. Electrical protection (LM2596, capacitor, USB isolation, RTS LED), mechanical safety, and camera synchronization require dedicated hardware testing.
