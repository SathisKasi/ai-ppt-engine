$pptx = "C:\Users\Admin\Downloads\Introduction_and_analysis_of_GPT_6_Astra_its_capabilities_pe_fixed.pptx"
try {
    $ppt = New-Object -ComObject PowerPoint.Application
    $pres = $ppt.Presentations.Open($pptx, [Microsoft.Office.Core.MsoTriState]::msoTrue, [Microsoft.Office.Core.MsoTriState]::msoFalse, [Microsoft.Office.Core.MsoTriState]::msoFalse)
    Write-Host "SUCCESSFULLY OPENED IN POWERPOINT! Slides:" $pres.Slides.Count
    $pres.Close()
    $ppt.Quit()
} catch {
    Write-Host "FAILED:" $_.Exception.Message
}
