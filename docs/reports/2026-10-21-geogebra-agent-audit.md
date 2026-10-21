# Kiểm thử agent GeoGebra — 21/10/2026

## Phạm vi

- Checkout đang mở: `feature/geo3d-viewer`, chưa có agent GeoGebra.
- Nguồn được kiểm thử: `origin/feature/geogebra-agent`, commit `f7da2dfc050a69a5fa9dc8b57e97c6d59518c719`.
- Xuất nguồn bằng `git archive` vào `/tmp/vision-agent-geogebra-audit`; không chuyển nhánh, không sửa mã ứng dụng.
- Đã đọc mã qua RepoMix: `/tmp/geogebra-agent-repomix.xml` (agents, tool, schema, compiler, frontend runtime và tests; loại `.env`).
- LLM thật: `deepseek-ai/DeepSeek-V4.1-Flash`, qua cấu hình hiện có trong `.env`. Chỉ nạp khóa vào tiến trình, không ghi khóa vào báo cáo.

## Kết luận

GeoGebra vẽ được đường thẳng song song Oy và cắt Ox. Trong trình duyệt thật, app `graphing` nhận cả `d=Line(A,B)` với `A=(2,0), B=(2,1)` lẫn `v: x=2`; giao điểm với `xAxis` là `(2,0)`.

Giới hạn nằm ở lớp tích hợp của repo:

1. `geometry3d/geogebra/schema.py:101–106` chặn mọi bước khác `function2d` khi `app="graphing"`. Bởi vậy `point`, `line`, `intersection` bị từ chối trước khi GeoGebra chạy. Đường thẳng đứng không phải đồ thị hàm `y=f(x)`.
2. `tools/geometry/construction_tool.py:16` đưa chính hạn chế đó vào hướng dẫn cho model: `graphing accepts only function2d`. Hướng dẫn chưa có ví dụ dựng đường thẳng đứng hoặc cách chuyển bài phẳng sang app `3d` với `z=0`.
3. Compiler hiện có hỗ trợ `Line(A,B)` tại `geometry3d/geogebra/compiler.py:64–65`, nên app `3d` là cách chạy được trong hợp đồng hiện tại.

Không tái hiện được nguyên văn lời từ chối trên máy khác. Model trong lần thử này có lúc chọn sai bước nhưng tự sửa thành công với đề đủ dữ kiện. Các kết quả dưới đây là từng lần chạy, không phải đánh giá tỷ lệ thành công.

## Kết quả LLM thật

| Đề thử | Kết quả |
|---|---|
| “Vẽ đường thẳng cắt trục hoành và song song với trục tung.” | 1 lần gọi tool, `needs_clarification` vì chưa xác định hoành độ giao điểm. Chưa tạo artifact. |
| “Vẽ trong mặt phẳng Oxy đường thẳng d đi qua A(2,0) và song song với trục tung. Đánh dấu giao điểm với trục hoành.” | Lần 1 chọn `graphing`, bị schema chặn; lần 2 chuyển `3d` nhưng thiếu điểm `O`, `X`; lần 3 chuẩn bị đúng. Artifact render thật thành công, giao điểm `(2,0,0)`. |
| Yêu cầu rõ app `3d`, A(2,0,0), B(2,1,0), Ox qua O và X, rồi dựng I | `prepared` ngay lần đầu. Artifact render thật thành công, I=(2,0,0). |

Model còn sinh `line(a=A,b=A)` ở đề 1 và lần đầu của đề 2. Một kiểm tra độc lập xác nhận tool hiện trả `prepared` cho cấu hình suy biến này trong app `3d`: validator chỉ kiểm tra loại điểm, chưa kiểm tra hai điểm phân biệt. Với đề 1, `unresolved_issues` khiến tool trả sớm trước khi kiểm tra spec. Đây là lỗ hổng bắt lỗi dựng hình, không phải bằng chứng GeoGebra thiếu khả năng vẽ.

## Kiểm chứng tự động

- Python: **34/34** test `test_geogebra*.py` qua `unittest discover`.
- Frontend: **10/10** unit test qua `npm run test:unit`.
- Playwright với GeoGebra thật: **4/4** ca trong `frontend/e2e/vertical-audit.spec.js` của bản xuất tạm:
  - Artifact chuẩn qua giao diện chat và viewer của repo: đường thẳng hiện và giao điểm đúng.
  - API GeoGebra `graphing` trực tiếp: cả đường qua hai điểm và phương trình `x=2` đều nhận và xác định.
  - Hai artifact của LLM thật chạy qua `executeArtifact`: đường thẳng hiện, giao điểm đúng.
- Assertion tọa độ dùng sai số `1e-8`; lần viết test đầu so sánh tuyệt đối gặp `-0` với `0`, đã sửa assertion và chạy lại đủ 4 ca.

Lệnh kiểm tra chính trong bản xuất tạm:

```bash
/tmp/vision-agent-geogebra-venv/bin/python -m unittest discover -s tests -p 'test_geogebra*.py'
cd frontend
npm run test:unit
npx playwright test e2e/vertical-audit.spec.js --config=playwright.audit.config.js --workers=1 --reporter=line
```

Môi trường Python tạm dùng Python 3.11 và các phiên bản LangChain/LangGraph của repo. Playwright dùng Chromium đã có trong cache qua cấu hình tạm. Không chạy full backend/supervisor hoặc Redis; kiểm tra live gọi trực tiếp `build_geometry_agent`, sau đó đưa artifact vào trình duyệt. SSE được giả lập trong ca kiểm tra giao diện.

## Hướng sửa đề xuất

- Cho phép các phép dựng phẳng trong app 2D và biên dịch điểm thành `(x,y)`, đồng thời từ chối tọa độ ngoài mặt phẳng và các phép chỉ có trong 3D. Chỉ gỡ validator là chưa đủ vì compiler hiện luôn phát điểm `(x,y,z)`.
- Thêm hướng dẫn và ví dụ đường thẳng đứng: hai điểm phân biệt cùng hoành độ, hoặc hỗ trợ phương trình ẩn qua schema có kiểm soát; không dùng `function2d` cho `x=c`.
- Chặn đường qua hai điểm trùng nhau và trả lỗi có thể sửa trước khi phát artifact.
- Thêm ca hồi quy từ đề tiếng Việt tới artifact và kết quả GeoGebra, vì test với model giả hiện chưa đo được việc model chọn phép dựng.

Chưa triển khai các thay đổi trên trong lần kiểm thử này.

## Bằng chứng cục bộ

- Kịch bản LLM và kết quả: `/tmp/vision-agent-geogebra-audit/audit_live.py`, `audit-live-{0,1,2}.json`.
- Kết quả tool thuần: `/tmp/vision-agent-geogebra-audit/audit-{graphing,3d}.json`.
- Kịch bản trình duyệt: `/tmp/vision-agent-geogebra-audit/frontend/e2e/vertical-audit.spec.js`.
- Ảnh: `/tmp/geogebra-vertical-3d.png`, `/tmp/geogebra-vertical-graphing.png`.
- Các tệp `/tmp` chỉ là bằng chứng của phiên này và có thể bị hệ điều hành dọn.

## Bản sửa sau khi thống nhất thiết kế

Triển khai trên nhánh `fix/geogebra-2d-3d`, xuất phát từ nhánh GeoGebra đã kiểm thử ở trên:

- 2D hỗ trợ điểm, đường thẳng, đoạn thẳng, đa giác, trung điểm, giao hai đường, hình chiếu lên đường và hàm số trong cùng artifact. Điểm nhận `[x,y]` hoặc `[x,y,0]`, phát lệnh `(x,y)`. Điểm 3D vẫn yêu cầu ba tọa độ; 2D từ chối z khác 0, mặt phẳng và mặt tường minh.
- Agent được hướng dẫn chọn chiều theo yêu cầu hiện tại, dựng `x=c` qua hai điểm phân biệt và khai báo điểm phụ đầy đủ. Hai điểm nhập trực tiếp trùng tọa độ hoặc hai tham chiếu cùng điểm bị chặn với lỗi `degenerate_line`. Các trường hợp suy biến chỉ xuất hiện sau phép dựng phụ vẫn được kiểm tra tại runtime.
- Kiểm tra API GeoGebra thật phát hiện Graphing Calculator chặn `Midpoint`, `ClosestPoint`, `Segment`, `Polygon`, dù nhận đường thẳng đứng. Geometry và Classic nhận tất cả các lệnh này cùng với hàm số. Viewer vì vậy dùng **Geometry** cho hình 2D có phép dựng và **Graphing Calculator** cho hình chỉ có hàm số. Trường `app="graphing"` trong hợp đồng artifact tiếp tục biểu thị 2D.
- Thêm fixture 2D gồm cả hình học và parabol, kiểm thử chuyển 2D → 3D → 2D trong cùng chat và mở lại hình cũ vẫn giữ chỉnh sửa.
- Thêm test model thật có thể bật riêng, kiểm tra tọa độ và tham chiếu toán học; xuất artifact để chạy tiếp trên viewer thật. Cách chạy ghi trong README.

Trước khi sửa hướng dẫn, test hội thoại thật thất bại: lượt 1 chọn nhầm 3D và lượt 3 thiếu phép dựng cần thiết. Sau sửa, lần xác minh cuối tạo đúng `graphing → 3d → graphing`, mỗi lượt một lần gọi tool. GeoGebra xác nhận giao điểm `(2,0)`, `(-1,0)`, trung điểm `(2,0,0)` và giá trị parabol tại x=-2,0,2 lần lượt là 4,0,4. Đây là kết quả quan sát của lần chạy, không phải bảo đảm mọi lần sinh của model.

Kết quả cuối:

- `unittest discover -s tests`: 42 test qua, 1 test model thật bỏ qua mặc định; bật riêng test model thật cũng qua.
- 5 ca kernel cũ qua bằng `python tests/test_geometry3d.py`.
- 10 unit test frontend qua.
- 10 ca Playwright qua, gồm 6 ca dùng GeoGebra thật và trong đó có ca chạy artifact của LLM thật.
- Build frontend thành công; Vite vẫn cảnh báo bundle lớn hơn 500 kB.
- Review độc lập không còn phát hiện cần sửa sau khi bổ sung kiểm tra nội dung toán học của artifact live.

Luồng SSE trong ca trình duyệt được giả lập; model và GeoGebra đều chạy thật. Chưa chạy toàn bộ backend với supervisor, research/vision và Redis.

## Sửa hiển thị sau phản hồi ảnh chụp màn hình

Đã chạy backend và frontend thật; một yêu cầu qua Vite proxy → supervisor → geometry agent trả artifact 2D và hoàn tất không lỗi.

Tái hiện ở viewport 1850×900 xác nhận `d` là đường thẳng `x=2`, nhưng màu mặc định `#6E6D73`, không có nhãn; app Geometry ẩn cả trục x và y dù truyền tham số `showAxes`. Hai đường dựng trông như hai trục nên hình dễ bị hiểu là chỉ có điểm. Applet còn bị cố định ở 900×620, để trống phần còn lại của workspace.

Viewer hiện bật trục/lưới bằng API sau khi dựng hình mới, tô đường/đoạn/đồ thị màu xanh, tăng độ dày và hiện nhãn. Kích thước applet theo vùng chứa và được cập nhật qua ResizeObserver. Tắt autoscale của deployggb để tránh scale chồng lên kích thước do API đặt khi thu nhỏ cửa sổ. XML đã lưu vẫn giữ chỉnh sửa của người dùng khi mở lại. Tham khảo các phương thức hiển thị và kích thước trong [GeoGebra Apps API](https://geogebra.github.io/docs/reference/en/GeoGebra_Apps_API/).

Ca hồi quy thật kiểm tra loại đối tượng, màu đường, trục/lưới và kích thước ở cả cửa sổ rộng lẫn sau khi thu nhỏ. Ảnh kiểm chứng của phiên: `/tmp/geogebra-display-fixed.png`, `/tmp/geogebra-display-fixed-small.png`.

Sau chỉnh hiển thị: 11/11 ca Playwright qua (gồm artifact LLM thật), 10/10 unit test frontend qua, build thành công. Backend và frontend vẫn chạy tại cổng 8000 và 5173.

## Mặt cầu và tiếp tuyến

Người dùng tiếp tục báo hình mặt cầu chỉ có điểm. Đề thực tế là xin một ví dụ bất kỳ về mặt cầu, tiếp tuyến theo phương cho trước, cả phương trình và hình minh họa. Hợp đồng tool trước đây thiếu `sphere`; `surface_explicit` chỉ diễn tả `z=f(x,y)`, không phải một mặt cầu nguyên vẹn. Nối các điểm bằng đoạn thẳng cũng không thay thế mặt cầu.

Đã thêm bước 3D `sphere` với tâm và bán kính hữu hạn dương, hoặc tâm và một điểm đi qua. Validator kiểm tra tham chiếu, loại điểm, trường loại trừ nhau, bán kính và trường hợp điểm đi qua trùng tâm nhập trực tiếp. Compiler phát `Sphere(center,radius)` hoặc `Sphere(center,through)`; viewer tô mặt cầu xanh trong suốt. Schema 2D từ chối bước này. Hướng dẫn agent yêu cầu tạo đối tượng mặt cầu thật, không thay bằng điểm lấy mẫu hay một bán cầu. Cú pháp dựa trên [Sphere Command](https://geogebra.github.io/docs/manual/en/commands/Sphere/).

Ví dụ kiểm chứng: S: x²+y²+z²=4, M=(2,0,0), d: (x,y,z)=(2,0,0)+t(0,1,0). GeoGebra xác nhận đối tượng thuộc loại `sphere`, có thể tích 32π/3 và khoảng cách tâm O tới đường d bằng 2. Kiểm tra cả fixture và artifact của model thật.

Trong một smoke test qua API, supervisor có lúc đổi yêu cầu đường tiếp tuyến thành mặt phẳng tiếp diện và model chọn ba điểm xác định mặt phẳng sai so với lời giải. Đã bổ sung hướng dẫn supervisor/geometry agent giữ đúng loại đối tượng. Ca live nay chạy qua supervisor, kiểm tra có đường thực sự tiếp xúc bằng khoảng cách từ tâm đến đường (không chấp nhận các đường trục tọa độ thay thế). Lần chạy cuối giữ đúng đường `d`, tạo đủ mặt cầu và tiếp tuyến; artifact tiếp tục được kiểm tra trên GeoGebra thật. Các phép dựng tổng quát khác vẫn chưa có cổng chứng minh mọi khẳng định trong lời giải.

Kiểm thử: 48 test Python qua và 2 ca live bỏ qua mặc định; ca live mặt cầu qua riêng. 13 ca Playwright đầy đủ qua với các artifact live đã xuất, 10 unit test frontend và build qua. Backend đã khởi động lại để nạp schema và prompt mới. Lịch sử backend dùng bộ nhớ nên cần tạo phiên chat mới khi thử lại sau lần khởi động này.

## Tra tài liệu qua tool, không đưa manual vào system prompt

Đã tích hợp snapshot chính thức từ `geogebra/manual`, commit `60a1a5e782e838b07182fea751846fae9689bf9a`: 525 trang AsciiDoc trong thư mục lệnh tiếng Anh, khoảng 622 KB. Tệp đóng gói nằm tại `geometry3d/geogebra/manual/commands.json`; mỗi kết quả tra cứu có URL trang công bố và URL tệp nguồn gắn commit. Script `scripts/sync_geogebra_docs.py` tạo lại snapshot từ checkout sạch. Đã tạo lại và so sánh trùng khớp từng byte.

Agent được cấp hai tool:

1. `search_geogebra_docs(query)`: agent chuyển ý định tiếng Việt thành truy vấn ngắn tiếng Anh; chỉ mục cục bộ tính điểm BM25 và ưu tiên tên trùng khớp, trả tối đa 5 kết quả với tóm tắt 240 ký tự mỗi trang.
2. `get_command_docs(command, offset)`: đọc đúng trang được chọn, giữ nguyên các chữ ký lệnh, ví dụ và lưu ý AsciiDoc; tối đa 4.000 ký tự mỗi lần, có `next_offset` cho trang dài.

System prompt chỉ hướng dẫn cách tra và hợp đồng dựng hình hiện tại, không chứa toàn bộ corpus. Nội dung trang đi vào ngữ cảnh qua ToolMessage. Giới hạn 8 lần tra mỗi yêu cầu độc lập với 3 lần chuẩn bị hình; yêu cầu tiếp theo đặt lại bộ đếm. Chưa cần embedding, vector database hoặc gọi mạng trong lượt chat.

Ca live từ câu tiếng Việt yêu cầu hình nón đã tự tìm và đọc trang `Cone` qua 3 lần gọi tool. Ca mặt cầu qua supervisor vẫn tạo được mặt cầu cùng đường tiếp tuyến đúng sau khi bổ sung tra cứu. Bộ Python cuối: 58 ca qua, 3 ca live bỏ qua mặc định; hai ca live tài liệu hình nón và mặt cầu được bật kiểm tra riêng và qua. Review phát hiện trang `3D_Commands` có tên bắt đầu bằng số chưa đọc được; đã tái hiện bằng test thất bại, sửa và kiểm tra lại.

Phần này giải quyết **truy xuất cú pháp liên quan**. Compiler có kiểu hiện tại vẫn chỉ nhận các operation đã định nghĩa; việc tìm thấy `Cone` trong manual không tự biến nó thành operation có thể thực thi. Agent được hướng dẫn nói rõ giới hạn tích hợp này, không dựng các điểm thay thế rồi báo đã vẽ hình và không quy giới hạn của repo thành giới hạn của GeoGebra. Bộ thực thi lệnh tổng quát kèm phản hồi runtime và kiểm chứng quan hệ hình học chưa được triển khai trong bước này.

## Nhãn minh họa ngắn thay phương trình

Theo phản hồi hình khó đọc vì nhãn chứa công thức, viewer đổi từ chế độ `NAME_VALUE` sang `NAME` mặc định. Mọi bước dựng có thể khai báo `caption` mô tả ngắn (1–80 ký tự, loại khoảng trắng đầu/cuối). Khi có caption, viewer dùng chế độ `CAPTION`, ví dụ `Tâm O`, `Mặt cầu (S)`, `Tiếp tuyến d`; không đổi id, tọa độ, phương trình hay quan hệ phụ thuộc. Phương trình vẫn xem trong bảng đại số và phần giải thích. Tiêu đề artifact hiện trên đầu workspace.

Đã bổ sung kiểm thử compiler xác nhận caption không thay đổi lệnh toán học và kiểm thử GeoGebra thật kiểm tra caption cùng chế độ nhãn trong XML. Ảnh kiểm chứng: `/tmp/geogebra-short-captions.png`. Kiểm thử cuối: 59 test Python qua (3 ca live bỏ qua mặc định), 14 ca Playwright qua, 10 unit test frontend qua và build thành công. Backend đã nạp schema/prompt mới; XML của hình cũ đã lưu vẫn giữ các chỉnh sửa trước đó, nên dùng hình mới để xem mặc định nhãn mới.

## Chẩn đoán miền diện tích giữa hai đồ thị

Người dùng báo lời giải nhắc vùng tô giữa f và g trên [-1,2], nhưng hình không tô. Trích dẫn của LLM có điều kiện: “nếu bạn dùng lệnh Integral(f,g,-1,2)”. Log tiến trình hiện chỉ lưu các lượt HTTP, không lưu nội dung artifact; chưa khôi phục được hai hàm hay chuỗi lệnh của đúng lượt đó. Vì vậy không khẳng định đã xem được artifact cũ của người dùng.

Kiểm tra mã cho thấy schema và compiler hiện không có phép dựng vùng tích phân, và không phát `Integral`/`IntegralBetween`. Chỉ thêm mô tả trong lời giải không tạo đối tượng hình học trong GeoGebra. Đây tiếp tục là giới hạn của compiler liệt kê operation; truy xuất tài liệu mới bổ sung chưa phải một bộ thực thi lệnh tổng quát.

Đã chạy probe độc lập trên GeoGebra thật với **ví dụ kiểm chứng**, không giả định là đúng đề người dùng: f=x², g=x+2, đoạn [-1,2]. Cả app graphing và geometry đều nhận `region=IntegralBetween(g,f,-1,2)`, đối tượng xác định và hiển thị, giá trị 4,5; đặt filling=0,5 tạo vùng tô rõ trên ảnh. Phiên bản GeoGebra này cũng nhận `Integral(f,g,-1,2)` như dạng tương thích, nên không kết luận rằng câu lệnh trong lời giải sai cú pháp. Tài liệu chuẩn trong snapshot có trang `IntegralBetween` mô tả miền giữa hai đồ thị; `Integral` mô tả các dạng tích phân khác, gồm miền dưới một hàm.

Hai ca probe đều qua; ảnh ở `/tmp/geogebra-integral-graphing.png` và `/tmp/geogebra-integral-geometry.png`, script tạm và log được giữ trong `/tmp`. Lần chẩn đoán này không thêm một operation Integral riêng và chưa thay đổi mã ứng dụng để tô miền. Cần bộ thực thi lệnh tổng quát và phản hồi kết quả render trước khi LLM được báo phần hiển thị đã hoàn tất; đồng thời cần lưu trace artifact để kiểm tra đúng lượt khi người dùng báo lỗi.

Người dùng đã cung cấp đúng bài: f=x²+1, g=x+3, giao điểm A(-1,2), B(2,5), cùng điểm phụ C(2,0), D(-1,0), X(1,0). Đã chạy lại probe với đúng f và g trên cả graphing và geometry: `region=IntegralBetween(g,f,-1,2)` tạo miền tô hiển thị, giá trị 4,5 và filling=0,5. Hai ca qua. Miền cần tô là f(x)≤y≤g(x), -1≤x≤2; Ox không phải biên của miền. Nếu dùng đa giác ABCD thì đó là miền dưới đường thẳng tới Ox, khác với miền cong cần tính. Đây là nhận xét về các điểm trong mô tả, không phải khẳng định artifact cũ đã chứa lệnh Polygon.

Ảnh đúng đề: `/tmp/geogebra-user-integral-graphing.png`, `/tmp/geogebra-user-integral-geometry.png`; script `/tmp/geogebra-user-integral-diagnostic.spec.js`, log `/tmp/geogebra-user-integral.log`. Kết quả chỉ xác nhận khả năng render trực tiếp; compiler của ứng dụng chưa được thay đổi trong lượt tái hiện này.


## Đã triển khai phát lệnh tổng quát và tô miền trong ứng dụng

Sau yêu cầu phải tô trực tiếp, đã mở rộng schema bằng bước `command` dùng đối số có cấu trúc, tra danh mục lệnh toán học từ snapshot manual và loại scripting. Các tham chiếu vẫn được kiểm tra phụ thuộc; biểu thức dùng parser hiện có. Không thêm operation Integral riêng. Lệnh chưa được app GeoGebra hỗ trợ hoặc đối tượng không xác định vẫn báo lỗi runtime; chưa có vòng tự sửa từ runtime về LLM.

Đúng bài f=x²+1, g=x+3: supervisor và model thật tạo `IntegralBetween(g,f,-1,2)` với `fill_opacity=0.5`. Artifact này được đưa qua viewer của ứng dụng và GeoGebra thật: vùng cong được tô màu cam, hiển thị, có độ tô 0,5 và giá trị 4,5. Ảnh kiểm chứng: `/tmp/geogebra-region-in-app.png`. Cùng cơ chế dựng được Cone với thể tích 16π/3, không bổ sung operation Cone.

Backend ghi trace `geometry_prepared` với request/artifact id, lệnh biên dịch và độ tô. Đây là xác nhận đã chuẩn bị/phát artifact, không phải xác nhận trình duyệt đã render. Hướng dẫn agent yêu cầu đặc tính được nói tới phải có trong artifact; không dùng một câu lệnh giả định trong lời giải thay cho tạo miền.

Kiểm chứng: 68 Python tests (64 qua, 4 live bỏ qua mặc định), kernel hình học qua, 10 frontend unit tests qua, 16 browser tests qua trên GeoGebra thật, frontend build qua. Ca tích phân với model thật bật riêng đã qua; browser suite dùng chính artifact đó. Review không phát hiện lỗi cần sửa trong đường lệnh tổng quát.
