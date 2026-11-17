// 점수판 구글 시트에 '점수판' 메뉴를 만들어요. (인터넷 게임에는 올라가지 않는 선생님 전용 코드예요)
// 사용법: 시트에서 확장 프로그램 → Apps Script 를 열고, 기존 Code.gs 맨 아래에 이 내용을 붙여넣고 저장해요.
// 시트를 새로고침하면 메뉴 '점수판 → 점수 전체 지우기'가 보여요.

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu("점수판")
    .addItem("점수 전체 지우기", "resetScores")
    .addToUi();
}

function resetScores() {
  var ui = SpreadsheetApp.getUi();
  var answer = ui.alert("점수 전체 지우기", "모든 점수를 지울까요? 되돌릴 수 없어요.", ui.ButtonSet.YES_NO);
  if (answer !== ui.Button.YES) return;
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName("점수");
  if (!sheet) return;
  var last = sheet.getLastRow();
  if (last > 1) sheet.deleteRows(2, last - 1);
  ui.alert("점수를 모두 지웠어요.");
}
