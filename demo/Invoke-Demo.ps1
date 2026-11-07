# Requires Windows PowerShell 5.1 or PowerShell 7 and a running API.
[CmdletBinding()]
param([string]$BaseUrl = 'http://127.0.0.1:8000')

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Net.Http
$http = New-Object System.Net.Http.HttpClient
$http.Timeout = [TimeSpan]::FromSeconds(20)
$BaseUrl = $BaseUrl.TrimEnd('/')

function Invoke-DemoRequest {
    param([string]$Method, [string]$Path, $Body, [int]$Expected = 200)
    $request = New-Object System.Net.Http.HttpRequestMessage
    $request.Method = New-Object System.Net.Http.HttpMethod($Method)
    $request.RequestUri = [Uri]"$BaseUrl$Path"
    if ($null -ne $Body) {
        $json = ConvertTo-Json -InputObject $Body -Depth 8 -Compress
        $request.Content = New-Object System.Net.Http.StringContent($json, [Text.Encoding]::UTF8, 'application/json')
    }
    $response = $null
    try {
        $response = $http.SendAsync($request).GetAwaiter().GetResult()
        $text = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
        $status = [int]$response.StatusCode
        Write-Host "$Method $Path -> $status $text"
        if ($status -ne $Expected) { throw "Expected HTTP $Expected; received $status" }
        return ($text | ConvertFrom-Json)
    }
    finally {
        if ($null -ne $response) { $response.Dispose() }
        $request.Dispose()
    }
}

function Assert-Demo {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
}

try {
    $runId = [Guid]::NewGuid().ToString('N')
    $customer = "C-$runId"
    $meter = "M-$runId"
    $today = [DateTime]::UtcNow.Date
    $firstDate = $today.AddDays(-2).ToString('yyyy-MM-dd')
    $secondDate = $today.AddDays(-1).ToString('yyyy-MM-dd')
    $messageDate = $today.ToString('yyyy-MM-dd')
    Write-Host "Demo run $runId against $BaseUrl (adds records; deletes nothing)"
    $null = Invoke-DemoRequest GET '/health' $null
    $null = Invoke-DemoRequest POST '/customers' @{ id = $customer; name = 'Interview Demo'; tariff_code = 'STANDARD' } 201
    $null = Invoke-DemoRequest POST '/meters' @{ id = $meter; customer_id = $customer; unit = 'kWh' } 201
    $null = Invoke-DemoRequest POST '/readings' @{ meter_id = $meter; reading_date = $firstDate; reading_value = 12450 } 201
    $null = Invoke-DemoRequest POST '/readings' @{ meter_id = $meter; reading_date = $secondDate; reading_value = 12820 } 201
    $bill = Invoke-DemoRequest POST "/bills/calculate/$meter" $null
    Assert-Demo ([decimal]::Parse([string]$bill.total_amount, [Globalization.CultureInfo]::InvariantCulture) -eq [decimal]168.39) 'Invoice total differs from EUR 168.39'

    $switch = @{
        request_id = "SW-$runId"; customer_id = $customer; meter_id = $meter
        old_supplier = 'DEFAULT'; new_supplier = 'DEMO-ENERGY'
        requested_date = [DateTime]::UtcNow.ToString('yyyy-MM-dd')
    }
    $accepted = Invoke-DemoRequest POST '/supplier-switches' $switch 201
    Assert-Demo ($accepted.status -eq 'COMPLETED') 'Switch was not completed'
    $history = Invoke-DemoRequest GET "/supplier-switches/$($switch.request_id)" $null
    Assert-Demo ($history.status -eq 'COMPLETED') 'Completed history was not preserved'
    $switch.request_id = "REJ-$runId"
    $switch.old_supplier = 'DEMO-ENERGY'
    $switch.requested_date = [DateTime]::UtcNow.ToString('yyyy-MM-dd')
    $rejected = Invoke-DemoRequest POST '/supplier-switches' $switch 201
    Assert-Demo ($rejected.status -eq 'REJECTED' -and $rejected.rejection_reason -eq 'New supplier must differ from old supplier') 'Expected unchanged-supplier rejection'
    $history = Invoke-DemoRequest GET "/supplier-switches/$($switch.request_id)" $null
    Assert-Demo ($history.status -eq 'REJECTED') 'Rejected history was not preserved'

    $message = @{
        control_record = @{ document_number = "OK-$runId"; message_type = 'METER_READING'; sender = 'DEMO'; receiver = 'UTILITIES' }
        segments = @(@{ segment_type = 'ZMETER'; meter_id = $meter; reading_date = $messageDate; reading = 12900 })
    }
    $ack = Invoke-DemoRequest POST '/market-messages/idoc' $message
    Assert-Demo ($ack.status -eq 'COMPLETED') 'Market message was not completed'
    $message.control_record.document_number = "FAIL-$runId"
    $message.segments[0].meter_id = "UNKNOWN-$runId"
    $failure = Invoke-DemoRequest POST '/market-messages/idoc' $message 404
    Assert-Demo ($failure.detail -eq 'Meter does not exist') 'Expected unknown-meter error'
    Write-Host "PASS: all demo assertions. Failed message ID: FAIL-$runId"
    Write-Host 'The FAILED record and reason are stored in SQLite; there is no message-history GET endpoint.'
}
finally { $http.Dispose() }
