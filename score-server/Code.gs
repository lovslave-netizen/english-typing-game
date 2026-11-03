// 영어 타자 게임 점수판 (Google Apps Script 웹앱)
// 점수는 이 스크립트가 붙어 있는 구글 시트의 '점수' 시트에만 쌓여요.
// 설정 방법은 README.md 를 봐 주세요.

var SHEET_NAME = "점수";
var MAX_SCORE = 100000;

function getSheet_() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName(SHEET_NAME) || ss.insertSheet(SHEET_NAME);
  if (sheet.getLastRow() === 0) sheet.appendRow(["날짜", "이름", "점수"]);
  return sheet;
}

function json_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}

// 게임 페이지가 점수판을 읽을 때: 상위 50명
function doGet() {
  var rows = getSheet_().getDataRange().getValues().slice(1);
  rows.sort(function (a, b) { return Number(b[2]) - Number(a[2]); });
  var top = rows.slice(0, 50).map(function (r) {
    return { name: String(r[1]), score: Number(r[2]) };
  });
  return json_({ ok: true, top: top });
}

// 점수판 전체 지우기: Apps Script 편집기에서 이 함수를 골라 ▶실행 하면 점수만 지워지고 제목 줄은 남아요.
function resetScores() {
  var sheet = getSheet_();
  var last = sheet.getLastRow();
  if (last > 1) sheet.deleteRows(2, last - 1);
}

// 게임 페이지가 점수를 저장할 때: { name, score }
function doPost(e) {
  var data;
  try {
    data = JSON.parse(e.postData.contents);
  } catch (err) {
    return json_({ ok: false, error: "bad json" });
  }
  var name = String(data.name || "").trim().slice(0, 10);
  var score = Math.floor(Number(data.score));
  if (!name || !(score >= 0 && score <= MAX_SCORE)) {
    return json_({ ok: false, error: "bad input" });
  }
  var lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    getSheet_().appendRow([new Date(), name, score]);
  } finally {
    lock.releaseLock();
  }
  return json_({ ok: true });
}
