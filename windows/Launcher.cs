using System;
using System.IO;
using System.Diagnostics;
using System.Drawing;
using System.Windows.Forms;
using Microsoft.Win32;
public class Launcher : Form {
 TextBox address; string config;
 [STAThread] public static void Main(){Application.EnableVisualStyles();Application.SetCompatibleTextRenderingDefault(false);Application.Run(new Launcher());}
 public Launcher(){Text="스쿠터 창고 연결";ClientSize=new Size(560,285);StartPosition=FormStartPosition.CenterScreen;FormBorderStyle=FormBorderStyle.FixedDialog;MaximizeBox=false;BackColor=Color.FromArgb(244,247,248);Font=new Font("Malgun Gothic",10);
 config=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"ScooterWarehouse","server.txt");
 var title=new Label{Text="Scooter Warehouse",Font=new Font("Segoe UI",22,FontStyle.Bold),Location=new Point(26,24),AutoSize=true};Controls.Add(title);
 Controls.Add(new Label{Text="휴대폰과 같은 서버 주소를 입력하세요.",Location=new Point(28,78),AutoSize=true});
 address=new TextBox{Location=new Point(28,111),Size=new Size(502,28),Text=File.Exists(config)?File.ReadAllText(config):"https://"};Controls.Add(address);
 var open=new Button{Text="창고 프로그램 열기",Location=new Point(28,160),Size=new Size(240,43),BackColor=Color.FromArgb(0,125,121),ForeColor=Color.White,FlatStyle=FlatStyle.Flat};open.Click+=(s,e)=>Connect();Controls.Add(open);AcceptButton=open;
 var local=new Button{Text="이 PC에서 로컬 테스트",Location=new Point(282,160),Size=new Size(248,43)};local.Click+=(s,e)=>{address.Text="http://127.0.0.1:8765";Connect();};Controls.Add(local);
 Controls.Add(new Label{Text="Chrome 전용 창으로 실행됩니다. 로컬 테스트는 서버를 먼저 실행하세요.",Location=new Point(28,229),Size=new Size(500,45),ForeColor=Color.DimGray});}
 void Connect(){try{Uri u;var value=address.Text.Trim();if(!Uri.TryCreate(value,UriKind.Absolute,out u)||!String.IsNullOrEmpty(u.UserInfo)||!(u.Scheme=="https"||(u.Scheme=="http"&&u.IsLoopback))||!String.IsNullOrEmpty(u.Query)||!String.IsNullOrEmpty(u.Fragment)){MessageBox.Show("HTTPS 서버 주소 또는 로컬 테스트 주소를 입력하세요.");return;}string chrome=null;string[] candidates={Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles),"Google","Chrome","Application","chrome.exe"),Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86),"Google","Chrome","Application","chrome.exe"),Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"Google","Chrome","Application","chrome.exe")};foreach(var p in candidates)if(File.Exists(p)){chrome=p;break;}if(chrome==null){MessageBox.Show("Google Chrome을 설치한 뒤 다시 실행하세요.");return;}
 Directory.CreateDirectory(Path.GetDirectoryName(config));File.WriteAllText(config,u.GetLeftPart(UriPartial.Authority));Process.Start(new ProcessStartInfo(chrome,"--app=\""+u.GetLeftPart(UriPartial.Authority)+"/\" --window-size=1440,960"){UseShellExecute=false});WindowState=FormWindowState.Minimized;
 }catch(Exception e){MessageBox.Show("연결 프로그램 실행 실패: "+e.Message);}}
}
