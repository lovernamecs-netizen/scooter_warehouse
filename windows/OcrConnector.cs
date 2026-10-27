using System;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Windows.Forms;
using Microsoft.Win32;

internal static class OcrConnector {
 const string Scheme="scooterwarehouse-ocr";
 static readonly string Home=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"ScooterWarehouse","OcrConnector");
 static readonly string Config=Path.Combine(Home,"program.txt");
 static bool ValidUri(string value){return String.Equals(value,"scooterwarehouse-ocr://open",StringComparison.Ordinal);}
 static string ProgramPath(string value){
  string p=Path.GetFullPath(value);
  if(!Path.IsPathRooted(value)||p.StartsWith("\\\\")||!File.Exists(p)||!String.Equals(Path.GetFileName(p),"ChatRegistrationOCR.exe",StringComparison.OrdinalIgnoreCase))throw new Exception("이 PC에 설치된 ChatRegistrationOCR.exe를 선택해주세요.");
  return p;
 }
 [STAThread] static int Main(string[] args){
  // Testable validation without touching registration or launching a process.
  if(args.Length==2 && args[0]=="--check-uri")return ValidUri(args[1])?0:2;
  if(args.Length==1 && args[0]=="--check-install"){
   try{ProgramPath(File.ReadAllText(Config,Encoding.UTF8));return 0;}catch{return 2;}
  }
  try{
   if(args.Length==1 && ValidUri(args[0])){
    if(!File.Exists(Config))throw new Exception("OCR 연결 설정을 먼저 실행해주세요.");
    string target=ProgramPath(File.ReadAllText(Config,Encoding.UTF8));
    Process.Start(new ProcessStartInfo(target){WorkingDirectory=Path.GetDirectoryName(target),UseShellExecute=false});return 0;
   }
   bool quiet=args.Length==2 && args[0]=="--install";
   if(args.Length!=0 && !quiet)throw new Exception("허용되지 않은 OCR 실행 요청입니다.");
   string selected;
   if(quiet)selected=args[1];
   else {using(var dialog=new OpenFileDialog()){dialog.Title="설치된 OCR 실행 파일 선택";dialog.Filter="ChatRegistrationOCR.exe|ChatRegistrationOCR.exe";dialog.CheckFileExists=true;if(dialog.ShowDialog()!=DialogResult.OK)return 1;selected=dialog.FileName;}}
   string exe=ProgramPath(selected);Directory.CreateDirectory(Home);
   string own=Process.GetCurrentProcess().MainModule.FileName;
   string installed=Path.Combine(Home,"ScooterWarehouseOcrConnector.exe");
   if(!String.Equals(own,installed,StringComparison.OrdinalIgnoreCase))File.Copy(own,installed,true);
   File.WriteAllText(Config,exe,new UTF8Encoding(false));
   using(var key=Registry.CurrentUser.CreateSubKey(@"Software\Classes\"+Scheme)){
    key.SetValue("","URL:Scooter Warehouse OCR");key.SetValue("URL Protocol","");
    using(var command=key.CreateSubKey(@"shell\open\command"))command.SetValue("","\""+installed+"\" \"%1\"");
   }
   if(!quiet)MessageBox.Show("연결되었습니다. 창고 프로그램의 등록증 OCR에서 ‘이 PC에서 열기’를 누르세요.","스쿠터 창고 OCR");return 0;
  }catch(Exception e){MessageBox.Show(e.Message,"스쿠터 창고 OCR",MessageBoxButtons.OK,MessageBoxIcon.Warning);return 1;}
 }
}
