<?php

include 'GnuPlot.php';
include 'graph-sensornet-cfg.php';

$ymin = 0;
$ymax = 100;
$hours = 168;
$width = 1000;
$height = 425;
$yLabel = 'Temp (F)';

$sensorName = '';

$debug = false;

if (key_exists('ymin', $_REQUEST))
  $ymin = preg_replace('/[^0-9\-]+/', '', $_REQUEST['ymin']);

if (key_exists('ymax', $_REQUEST))
  $ymax = preg_replace('/[^0-9\-.]+/', '', $_REQUEST['ymax']);

if (key_exists('hours', $_REQUEST))
  $hours = preg_replace('/[^0-9\-.]+/', '', $_REQUEST['hours']);

if (key_exists('showFreezing', $_REQUEST))
  $showFreezing = True;
  
if (key_exists('width', $_REQUEST))
  $width = preg_replace('/[^0-9\-]+/', '', $_REQUEST['width']);
  
if (key_exists('height', $_REQUEST))
  $height = preg_replace('/[^0-9\-]+/', '', $_REQUEST['height']);
  
//$sensorName = preg_replace('/[^a-z0-9A-Z//]+/', '', $_REQUEST['sensorName']);

if (key_exists('ylabel', $_REQUEST))
  $yLabel = $_REQUEST['ylabel'];

if (key_exists('sensorName', $_REQUEST))
  $sensorNames = preg_replace('/[^a-z0-9A-Z_,\/]+/', '', $_REQUEST['sensorName']);

$sensorArray = explode(',', $sensorNames);



//$sensorName = $_REQUEST['sensorName'];

$plot = new GnuPlot;

#$plot->setGraphTitle('Temperature Graph');

$plot->setTimeFormatString("%H:%M");

if ($hours > 168)
{
  $plot->setTimeFormatString("%b %d");
  $xtics = 604800;
  $mxtics = 4;
}
else if ($hours > 24)
{
  $plot->setTimeFormatString("%b %d");
  $xtics = 86400;
  $mxtics = 4;
}
else if ($hours > 4)
{
  $plot->setTimeFormatString("%b %d  %H:%M");
  $xtics = 14400;
  $mxtics = 2;
}
else
{
  $plot->setTimeFormatString("%H:%M");
  $xtics = 14400;
  $mxtics = 2;
}
$plot->setXTimeFormat("%Y:%m:%d:%H:%M:%S");

// Grab these now to override ones determined automatically above
if (key_exists('xtics', $_REQUEST))
  $xtics = preg_replace('/[^0-9\-]+/', '', $_REQUEST['xtics']);
  
if (key_exists('mxtics', $_REQUEST))
  $mxtics = preg_replace('/[^0-9\-]+/', '', $_REQUEST['mxtics']);
  

$plot->setWidth($width);
$plot->setHeight($height);
$plot->setYLabel($yLabel);
$plot->show32($showFreezing);

$plot->setXtics($xtics);
$plot->setMxtics($mxtics);

//$plot->setYRange(32, 100);
$plot->setYRange($ymin, $ymax);

$deltaHours = sprintf("now +%d minutes", $hours*60/48);
$dt = new DateTime($deltaHours, new DateTimeZone("UTC"));
$endTime = $dt->format(DateTime::ISO8601);
$dt->setTimezone(new DateTimeZone('America/Denver'));
$endTimeGnuplot = $dt->format('Y:m:d:H:i:s');

$deltaHours = sprintf("-%d hours", $hours);
$dt = new DateTime($deltaHours, new DateTimeZone("UTC"));
$startTime = $dt->format(DateTime::ISO8601);
$dt->setTimezone(new DateTimeZone('America/Denver'));
$startTimeGnuplot = $dt->format('Y:m:d:H:i:s');

$plot->setXRange($startTimeGnuplot, $endTimeGnuplot);

$arrayIdx = -1;

foreach($sensorArray as $sensorName)
{
  $arrayIdx += 1;

  $url = 'http://localhost:8082/gethistory/' . $sensorName . '?start='.urlencode($startTime).'&end='.urlencode($endTime);

  $data = file_get_contents($url);
  $jsdata = json_decode($data);

  if (0 && $debug == true)
  {
    print 'url=' . $url . '<br>';
    print '<pre>';
    print_r($jsdata);
    print '</pre>';
  }


  $isTemperature = false;
  $explodedSensorName = explode('/', $sensorName);
  
  if (end($explodedSensorName) == "temperature")
    $isTemperature = true;

  $sensorPath = implode("/", array_slice($explodedSensorName, 0, -1));
  if($sensorPrettyNames[$sensorPath])
  {
    $title = $sensorPrettyNames[$sensorPath];
  }
  else 
  {
    $title = $sensorName;
  }

  if(empty($jsdata))
  {
    // Assign dummy value if empty
    $jsdata = json_decode('[{"time": "1900-01-01T00:00:00-00:00", "value": "0"}]');
    $title .= " [*]";
  }

  $plot->setTitle($arrayIdx, $title);

  foreach($jsdata as $datapt)
  {
    $localDT = new DateTime($datapt->time, new DateTimeZone("UTC"));
    $localDT->setTimezone(new DateTimeZone('America/Denver'));
    $pointTime = $localDT->format('Y:m:d:H:i:s');
    if ($debug)
      print $pointTime . ' ' . $datapt->value . '<br>';

    // Need to know units this came in vs.units displayed
    if ($isTemperature)
      $yval = $datapt->value * 1.8 + 32.0; //barometric_pressure * 0.0002953;
    else
      $yval = $datapt->value;

    $plot->push($pointTime, $yval, $arrayIdx);
  }
}

if (!$debug)
{
  $doPNG = true;
  if (!$doPNG)
  {
    header('Content-type: image/svg+xml');
    echo $plot->get(GnuPlot::TERMINAL_SVG);
  } else {
    header('Content-type: image/png');
    echo $plot->get(GnuPlot::TERMINAL_PNG);
  }

}
?>
