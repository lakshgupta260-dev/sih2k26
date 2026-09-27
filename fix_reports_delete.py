import re

with open('frontend/src/pages/project/Reports.tsx', 'r', encoding='utf-8') as f:
    code = f.read()

delete_mutation = '''
  const deleteMutation = useMutation({
    mutationFn: (reportId: string) => generatedReportsApi.delete(projectId, reportId),
    onSuccess: () => {
      toast("Report deleted", "success");
      queryClient.invalidateQueries({ queryKey: ["generated-reports", projectId] });
    },
    onError: (err) => {
      if (err instanceof ApiError) {
        toast(err.message, "error");
      } else {
        toast("Failed to delete report", "error");
      }
    },
  });
'''

code = code.replace('  const requestMutation = useMutation({', delete_mutation + '\n  const requestMutation = useMutation({')

dropdown_item = '''
                        <DropdownSeparator />
                        <DropdownItem
                          icon={<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" className="h-3.5 w-3.5 text-rose-500"><path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/><line x1="10" x2="10" y1="11" y2="17"/><line x1="14" x2="14" y1="11" y2="17"/></svg>}
                          className="!text-rose-500 hover:!bg-rose-500/10"
                          onSelect={() => {
                            if (window.confirm("Are you sure you want to delete this report?")) {
                              deleteMutation.mutate(r.id);
                            }
                            close();
                          }}
                        >
                          Delete report
                        </DropdownItem>
'''

code = code.replace('                        <DropdownSeparator />\n                        <DropdownItem\n                          icon={<Copy className="h-3.5 w-3.5" />}', dropdown_item + '\n                        <DropdownItem\n                          icon={<Copy className="h-3.5 w-3.5" />}')

with open('frontend/src/pages/project/Reports.tsx', 'w', encoding='utf-8') as f:
    f.write(code)
