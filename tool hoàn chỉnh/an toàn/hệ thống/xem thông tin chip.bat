@echo off
chcp 65001 > nul

powershell -NoProfile -Command ^
  "$cpu = Get-CimInstance Win32_Processor;" ^
  "$archMap = @{ 0='x86 (32-bit)'; 1='MIPS'; 2='Alpha'; 3='PowerPC'; 5='ARM'; 6='ia64 (Itanium)'; 9='x64 (64-bit)'; 12='ARM64' };" ^
  "$archName = if ($archMap.ContainsKey([int]$cpu.Architecture)) { $archMap[[int]$cpu.Architecture] } else { 'Không xác định (' + $cpu.Architecture + ')' };" ^
  "$status = if ($cpu.VirtualizationFirmwareEnabled) { 'Đang bật' } else { 'Đang tắt' };" ^
  "Write-Output '================ THÔNG TIN CHI TIẾT CPU ================';" ^
  "Write-Output ('Tên chip: ' + $cpu.Name.Trim());" ^
  "Write-Output ('Hãng sản xuất: ' + $cpu.Manufacturer);" ^
  "Write-Output ('Mô tả chi tiết: ' + $cpu.Caption);" ^
  "Write-Output ('Kiến trúc chip: ' + $archName);" ^
  "Write-Output ('Số lượng lõi vật lý (Cores): ' + $cpu.NumberOfCores);" ^
  "Write-Output ('Số lượng luồng xử lý (Threads): ' + $cpu.NumberOfLogicalProcessors);" ^
  "Write-Output ('Xung nhịp tối đa: ' + $cpu.MaxClockSpeed + ' MHz');" ^
  "Write-Output ('Xung nhịp hiện tại: ' + $cpu.CurrentClockSpeed + ' MHz');" ^
  "Write-Output ('Bộ nhớ đệm L2 (Cache): ' + $cpu.L2CacheSize + ' KB');" ^
  "Write-Output ('Bộ nhớ đệm L3 (Cache): ' + $cpu.L3CacheSize + ' KB');" ^
  "Write-Output ('Hỗ trợ ảo hóa (Virtualization): ' + $status);" ^
  "Write-Output ('Mức tải CPU hiện tại: ' + $cpu.LoadPercentage + ' %');" ^
  "Write-Output ('Mã định danh (Processor ID): ' + $cpu.ProcessorId);" ^
  "Write-Output ('Chân cắm (Socket): ' + $cpu.SocketDesignation);" ^
  "Write-Output '========================================================'"

pause
