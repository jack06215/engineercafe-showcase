import Snackbar from '@mui/material/Snackbar';

import { QueryView } from '@/components/ui/QueryView';
import { DeskView } from '@/features/desk/components/DeskView';
import { useDesk } from '@/features/desk/hooks/useDesk';

export const DeskPage = () => {
  const { desk, actions, message, clearMessage, busyItemId, replanning } =
    useDesk();
  return (
    <>
      <QueryView query={desk}>
        {(data) => (
          <DeskView
            desk={data}
            actions={actions}
            now={new Date()}
            busyItemId={busyItemId}
            replanning={replanning}
          />
        )}
      </QueryView>
      <Snackbar
        open={message !== null}
        message={message}
        onClose={clearMessage}
        autoHideDuration={6000}
      />
    </>
  );
};
