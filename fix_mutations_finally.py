import re

with open('frontend/src/pages/project/Reports.tsx', 'r', encoding='utf-8') as f:
    code = f.read()

new_mutation = '''  const deleteMutation = useMutation({
    mutationFn: (reportId: string) => generatedReportsApi.delete(projectId, reportId),
    onMutate: async (reportId: string) => {
      await queryClient.cancelQueries({ queryKey: ["generated-reports", projectId] });
      const previous = queryClient.getQueryData(["generated-reports", projectId]);
      queryClient.setQueryData(["generated-reports", projectId], (old: any) => {
        if (!old) return old;
        return {
          ...old,
          items: old.items.filter((r: any) => r.id !== reportId),
        };
      });
      return { previous };
    },
    onSuccess: () => {
      toast("Report deleted", "success");
    },
    onError: (err, reportId, context: any) => {
      queryClient.setQueryData(["generated-reports", projectId], context?.previous);
      if (err instanceof ApiError) {
        toast(err.message, "error");
      } else {
        toast("Failed to delete report", "error");
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["generated-reports", projectId] });
    },
  });

  const requestMutation = useMutation({'''

code = re.sub(r'  const deleteMutation = useMutation\(\{[\s\S]*?  const requestMutation = useMutation\(\{', new_mutation, code)

with open('frontend/src/pages/project/Reports.tsx', 'w', encoding='utf-8') as f:
    f.write(code)
