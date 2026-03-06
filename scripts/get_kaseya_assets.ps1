param(
  [int]$Top = 100,
  [int]$Skip = 0
)

py -3 scripts/kaseya_client.py --top $Top --skip $Skip
